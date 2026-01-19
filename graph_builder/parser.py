"""
Data parser for CSV and Excel files with streaming support.
"""

import json
import hashlib
import logging
from typing import Generator, Optional, Dict, List, Any
from pathlib import Path

import pandas as pd

from .utils import safe_float, safe_int, safe_str, parse_boolean
from .config import Config


logger = logging.getLogger('graph_builder')


class DataParser:
    """
    Parse CSV/Excel files with streaming support and error handling.

    Handles:
    - Large files via chunked reading
    - Skills JSON parsing
    - Error logging to bad_rows
    """

    def __init__(self, config: Config):
        self.config = config
        self.bad_rows: List[Dict[str, Any]] = []
        self.total_rows = 0
        self.parsed_rows = 0
        self._columns = []

    def parse(self) -> Generator[Dict[str, Any], None, None]:
        """
        Parse input file and yield rows one at a time.

        Yields:
            Dict containing parsed job data
        """
        input_path = Path(self.config.input_path)
        ext = input_path.suffix.lower()

        if ext == '.csv':
            yield from self._parse_csv()
        elif ext in ['.xlsx', '.xls']:
            yield from self._parse_excel()
        else:
            raise ValueError(f"Unsupported file format: {ext}")

        logger.info(
            f"Parsing complete: {self.parsed_rows}/{self.total_rows} rows "
            f"({len(self.bad_rows)} failures)"
        )

    def _parse_csv(self) -> Generator[Dict[str, Any], None, None]:
        """Parse CSV file in chunks."""
        logger.info(f"Reading CSV: {self.config.input_path}")

        # Try multiple encodings
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        encoding_used = None

        for encoding in encodings:
            try:
                sample = pd.read_csv(self.config.input_path, nrows=1, encoding=encoding)
                encoding_used = encoding
                logger.info(f"Using encoding: {encoding}")
                break
            except UnicodeDecodeError:
                continue

        if not encoding_used:
            raise ValueError(f"Could not determine file encoding. Tried: {encodings}")

        try:
            # First, get columns
            sample = pd.read_csv(self.config.input_path, nrows=1, encoding=encoding_used)
            self._columns = list(sample.columns)
            logger.info(f"Found {len(self._columns)} columns")

            # Read in chunks
            chunks = pd.read_csv(
                self.config.input_path,
                chunksize=self.config.chunk_size,
                dtype=str,  # Read all as string initially
                na_values=['', 'NA', 'N/A', 'null', 'NULL', 'None', 'nan'],
                keep_default_na=True,
                low_memory=False,
                encoding=encoding_used
            )

            for chunk_num, chunk in enumerate(chunks):
                logger.debug(f"Processing chunk {chunk_num + 1}")

                for idx, row in chunk.iterrows():
                    self.total_rows += 1

                    try:
                        parsed = self._parse_row(row, idx)
                        if parsed:
                            self.parsed_rows += 1
                            yield parsed
                    except Exception as e:
                        self._log_bad_row(idx, row, str(e))

                # Progress logging
                if self.total_rows % 10000 == 0:
                    logger.info(f"Processed {self.total_rows:,} rows...")

        except Exception as e:
            logger.error(f"Failed to read CSV: {e}")
            raise

    def _parse_excel(self) -> Generator[Dict[str, Any], None, None]:
        """Parse Excel file."""
        logger.info(f"Reading Excel: {self.config.input_path}")

        try:
            # Read entire Excel file (chunking not well supported)
            df = pd.read_excel(
                self.config.input_path,
                dtype=str,
                na_values=['', 'NA', 'N/A', 'null', 'NULL', 'None', 'nan']
            )

            self._columns = list(df.columns)
            logger.info(f"Found {len(self._columns)} columns, {len(df):,} rows")

            for idx, row in df.iterrows():
                self.total_rows += 1

                try:
                    parsed = self._parse_row(row, idx)
                    if parsed:
                        self.parsed_rows += 1
                        yield parsed
                except Exception as e:
                    self._log_bad_row(idx, row, str(e))

                # Progress logging
                if self.total_rows % 10000 == 0:
                    logger.info(f"Processed {self.total_rows:,} rows...")

        except Exception as e:
            logger.error(f"Failed to read Excel: {e}")
            raise

    def _parse_row(self, row: pd.Series, row_idx: int) -> Optional[Dict[str, Any]]:
        """
        Parse a single row into structured data.

        Args:
            row: pandas Series representing a row
            row_idx: Row index for error tracking

        Returns:
            Parsed row dict or None if parsing fails
        """
        # Parse skills JSON first (most likely to fail)
        skills_raw = safe_str(row.get(self.config.skills_column, ''))
        skills = self._parse_skills_json(skills_raw, row_idx)

        # Generate job ID
        job_id = self._get_job_id(row, row_idx)

        # Get category
        category = safe_str(row.get(self.config.category_column, ''))
        if not category:
            category = safe_str(row.get(self.config.fallback_category_column, ''))

        # Parse work from home
        wfh_raw = safe_str(row.get('Work From Home', ''))
        wfh = parse_boolean(wfh_raw)
        wfh_str = 'yes' if wfh is True else ('no' if wfh is False else '')

        return {
            'job_id': job_id,
            'job_title': safe_str(row.get('Job Title', '')),
            'company_name': safe_str(row.get('Company Name', '')),
            'posted_at': safe_str(row.get('Posted At', '')),
            'schedule_type': safe_str(row.get('Schedule Type', '')),
            'work_from_home': wfh_str,
            'district': safe_str(row.get('District', '')),
            'nco_code': safe_str(row.get('NCO Code', '')),
            'group_name': safe_str(row.get('Group', '')),
            'assigned_occupation_group': category,
            'hybrid_nco_jd': safe_str(row.get('Hybrid NCO JD', '')),
            'token_count': safe_int(row.get('token_count', 0)),
            'highest_similarity_spec': safe_str(row.get('Highest Similarity Spec', '')),
            'highest_similarity_score': safe_float(row.get('Highest Similarity Score Spec', 0)),
            'salary_mean': safe_float(row.get('salary_mean_inr_month', 0)),
            'salary_currency': safe_str(row.get('salary_currency_unit', '')),
            'salary_source': safe_str(row.get('salary_source', '')),
            'skills': skills,
            '_row_idx': row_idx
        }

    def _get_job_id(self, row: pd.Series, row_idx: int) -> str:
        """Generate or extract job ID."""
        if self.config.job_id_column != 'auto':
            job_id = safe_str(row.get(self.config.job_id_column, ''))
            if job_id:
                return job_id

        # Generate deterministic ID from unique combination
        title = safe_str(row.get('Job Title', ''))
        company = safe_str(row.get('Company Name', ''))
        district = safe_str(row.get('District', ''))

        unique_key = f"{title}|{company}|{district}|{row_idx}"
        hash_val = hashlib.md5(unique_key.encode()).hexdigest()[:16]

        return hash_val

    def _parse_skills_json(self, text: str, row_idx: int) -> List[Dict[str, Any]]:
        """
        Parse skills JSON array.

        Expected format:
        [
            {"skill": "Python", "bucket": "Advanced", "mapping_similarity": 0.9, "thinking": "..."},
            ...
        ]

        Returns:
            List of skill dicts, or empty list on failure
        """
        if not text or text.strip() == '':
            return []

        try:
            skills = json.loads(text)

            if not isinstance(skills, list):
                logger.warning(f"Row {row_idx}: skills is not a list")
                return []

            # Validate and clean each skill entry
            valid_skills = []
            for skill_entry in skills:
                if not isinstance(skill_entry, dict):
                    continue

                skill_label = safe_str(skill_entry.get('skill', ''))
                if not skill_label:
                    continue

                valid_skills.append({
                    'skill': skill_label,
                    'bucket': safe_str(skill_entry.get('bucket', '')),
                    'mapping_similarity': safe_float(skill_entry.get('mapping_similarity', 0)),
                    'thinking': safe_str(skill_entry.get('thinking', ''))
                })

            return valid_skills

        except json.JSONDecodeError as e:
            # Log but don't raise - we want to continue processing
            logger.debug(f"Row {row_idx}: JSON parse error - {e}")
            raise ValueError(f"Invalid skills JSON: {e}")

    def _log_bad_row(self, row_idx: int, row: pd.Series, error: str):
        """Log a failed row to bad_rows list."""
        self.bad_rows.append({
            'row_idx': row_idx,
            'job_title': safe_str(row.get('Job Title', 'unknown')),
            'company_name': safe_str(row.get('Company Name', 'unknown')),
            'error': error
        })

        if len(self.bad_rows) <= 10:
            logger.warning(f"Row {row_idx} failed: {error}")
        elif len(self.bad_rows) == 11:
            logger.warning("Suppressing further bad row warnings...")

    def get_bad_rows_df(self) -> pd.DataFrame:
        """Get bad rows as DataFrame for export."""
        return pd.DataFrame(self.bad_rows)

    @property
    def columns(self) -> List[str]:
        """Get list of columns from input file."""
        return self._columns
