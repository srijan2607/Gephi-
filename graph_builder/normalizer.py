"""
Skill canonicalization module.

This module handles the critical task of normalizing skill labels
to create proper overlap across jobs.
"""

import re
import logging
from typing import Dict, Set, List, Optional, Any, Generator
from collections import defaultdict

import pandas as pd

from .utils import slugify


logger = logging.getLogger('graph_builder')


class SkillNormalizer:
    """
    Normalize and canonicalize skill labels.

    Key functions:
    - Normalize text (lowercase, whitespace, punctuation)
    - Generate canonical keys for deduplication
    - Track aliases (original variants)
    - Merge identical skills across jobs
    """

    def __init__(self):
        # skill_key -> SkillEntry
        self.skill_dictionary: Dict[str, Dict[str, Any]] = {}

        # original_label -> skill_key (for lookup)
        self.alias_map: Dict[str, str] = {}

        # Statistics
        self.raw_skill_count = 0
        self.normalized_skill_count = 0

    def process_all(self, data: List[Dict]) -> List[Dict]:
        """
        Process all data in two passes:
        1. Build skill dictionary
        2. Return data with normalized skill references

        Args:
            data: List of parsed row dicts

        Returns:
            Same data (skills now reference canonical keys)
        """
        logger.info("Building skill dictionary...")

        # Pass 1: Build dictionary
        for row in data:
            for skill_entry in row.get('skills', []):
                self._register_skill(skill_entry)

        logger.info(
            f"Skill normalization complete: {self.raw_skill_count:,} raw -> "
            f"{len(self.skill_dictionary):,} canonical "
            f"({self._dedup_ratio():.1%} reduction)"
        )

        # Log top skills
        self._log_top_skills(10)

        return data

    def process_streaming(self, data_generator: Generator) -> Generator:
        """
        Process data in streaming mode.

        Note: For streaming, we do a single pass where we build
        the dictionary as we go. This means the dictionary is
        complete only after iteration finishes.

        Args:
            data_generator: Generator yielding parsed rows

        Yields:
            Parsed rows (same as input)
        """
        for row in data_generator:
            # Register skills as we encounter them
            for skill_entry in row.get('skills', []):
                self._register_skill(skill_entry)
            yield row

    def _register_skill(self, skill_entry: Dict[str, Any]) -> Optional[str]:
        """
        Register a skill in the dictionary.

        Args:
            skill_entry: Dict with 'skill', 'bucket', 'mapping_similarity', etc.

        Returns:
            Canonical key if registered, None if skipped
        """
        raw_label = skill_entry.get('skill', '')
        if not raw_label or not isinstance(raw_label, str):
            return None

        raw_label = raw_label.strip()
        if not raw_label:
            return None

        self.raw_skill_count += 1

        # Normalize and get canonical key
        normalized = self._normalize(raw_label)
        if not normalized:
            return None

        # Skip very short skills
        if len(normalized) < 2:
            logger.debug(f"Skipping short skill: '{raw_label}'")
            return None

        # Skip very long skills (likely descriptions)
        if len(normalized) > 100:
            logger.debug(f"Skipping long skill: '{raw_label[:50]}...'")
            return None

        # Skip numeric-only
        if re.match(r'^[\d\s.,-]+$', normalized):
            return None

        canonical_key = slugify(normalized)
        if not canonical_key:
            return None

        # Register in dictionary
        if canonical_key not in self.skill_dictionary:
            self.skill_dictionary[canonical_key] = {
                'canonical_key': canonical_key,
                'canonical_label': self._to_title_case(raw_label),
                'aliases': set(),
                'occurrence_count': 0,
                'max_similarity': 0.0,
                'sum_similarity': 0.0,
                'buckets': set()
            }

        entry = self.skill_dictionary[canonical_key]
        entry['aliases'].add(raw_label)
        entry['occurrence_count'] += 1

        similarity = skill_entry.get('mapping_similarity', 0)
        if isinstance(similarity, (int, float)):
            entry['max_similarity'] = max(entry['max_similarity'], similarity)
            entry['sum_similarity'] += similarity

        bucket = skill_entry.get('bucket', '')
        if bucket:
            entry['buckets'].add(bucket)

        # Track alias mapping
        self.alias_map[raw_label] = canonical_key

        return canonical_key

    def _normalize(self, raw_label: str) -> str:
        """
        Normalize skill label to canonical form.

        Steps:
        1. Strip whitespace
        2. Lowercase
        3. Remove trailing punctuation
        4. Normalize whitespace
        5. Normalize dashes/slashes
        6. Expand common abbreviations
        """
        s = raw_label.strip()
        if not s:
            return ""

        # Lowercase
        s = s.lower()

        # Remove trailing punctuation
        s = re.sub(r'[.,:;!?]+$', '', s)

        # Normalize whitespace (collapse multiple spaces)
        s = re.sub(r'\s+', ' ', s)

        # Normalize Unicode dashes to hyphen
        s = s.replace('–', '-')  # en-dash
        s = s.replace('—', '-')  # em-dash
        s = s.replace('−', '-')  # minus sign

        # Normalize slashes to hyphens
        s = re.sub(r'\s*/\s*', '-', s)

        # Normalize spaces around hyphens
        s = re.sub(r'\s*-\s*', '-', s)

        # Expand common abbreviations
        s = re.sub(r'\b&\b', ' and ', s)
        s = re.sub(r'\bw/\b', 'with ', s)
        s = re.sub(r'\bw/o\b', 'without ', s)

        # Collapse multiple spaces again after expansions
        s = re.sub(r'\s+', ' ', s)

        return s.strip()

    def _to_title_case(self, text: str) -> str:
        """Convert to title case, preserving acronyms."""
        words = text.split()
        result = []

        for word in words:
            # Keep all-caps words (acronyms) as-is
            if word.isupper() and len(word) <= 5:
                result.append(word)
            else:
                result.append(word.capitalize())

        return ' '.join(result)

    def get_skill_id(self, raw_label: str) -> Optional[str]:
        """
        Get the skill node ID for a raw label.

        Args:
            raw_label: Original skill label from data

        Returns:
            Skill ID like "skill:python-programming" or None
        """
        if not raw_label:
            return None

        raw_label = raw_label.strip()
        canonical_key = self.alias_map.get(raw_label)

        if canonical_key:
            return f"skill:{canonical_key}"

        # Try normalizing on-the-fly
        normalized = self._normalize(raw_label)
        canonical_key = slugify(normalized)

        if canonical_key and canonical_key in self.skill_dictionary:
            return f"skill:{canonical_key}"

        return None

    def get_canonical_label(self, skill_id: str) -> str:
        """Get the canonical label for a skill ID."""
        key = skill_id.replace('skill:', '')
        entry = self.skill_dictionary.get(key, {})
        return entry.get('canonical_label', key)

    def export_dictionary(self) -> pd.DataFrame:
        """Export skill dictionary as DataFrame."""
        records = []

        for key, entry in self.skill_dictionary.items():
            avg_sim = (
                entry['sum_similarity'] / entry['occurrence_count']
                if entry['occurrence_count'] > 0 else 0
            )

            records.append({
                'skill_id': f"skill:{key}",
                'canonical_key': key,
                'canonical_label': entry['canonical_label'],
                'aliases': '|'.join(sorted(entry['aliases'])),
                'alias_count': len(entry['aliases']),
                'occurrence_count': entry['occurrence_count'],
                'max_similarity': round(entry['max_similarity'], 4),
                'avg_similarity': round(avg_sim, 4),
                'buckets': '|'.join(sorted(entry['buckets']))
            })

        df = pd.DataFrame(records)

        # Sort by occurrence count descending
        if len(df) > 0:
            df = df.sort_values('occurrence_count', ascending=False)

        return df

    def _dedup_ratio(self) -> float:
        """Calculate deduplication ratio."""
        if self.raw_skill_count == 0:
            return 0.0
        return 1 - (len(self.skill_dictionary) / self.raw_skill_count)

    def _log_top_skills(self, n: int = 10):
        """Log the top N skills by occurrence."""
        sorted_skills = sorted(
            self.skill_dictionary.items(),
            key=lambda x: x[1]['occurrence_count'],
            reverse=True
        )[:n]

        logger.info(f"Top {n} skills by occurrence:")
        for key, entry in sorted_skills:
            logger.info(
                f"  {entry['canonical_label']}: {entry['occurrence_count']:,} jobs, "
                f"{len(entry['aliases'])} variants"
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get normalization statistics."""
        return {
            'raw_skill_strings': self.raw_skill_count,
            'canonical_skills': len(self.skill_dictionary),
            'dedup_ratio': round(self._dedup_ratio(), 4),
            'avg_aliases_per_skill': round(
                sum(len(e['aliases']) for e in self.skill_dictionary.values()) /
                max(len(self.skill_dictionary), 1),
                2
            )
        }
