"""
Configuration and CLI argument parsing.
"""

import argparse
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Config:
    """Configuration for the graph builder."""

    # Required
    input_path: str = ""
    output_dir: str = "./output"

    # Output format options
    formats: List[str] = field(default_factory=lambda: ["csv", "graphml"])
    drop_thinking: bool = True
    include_aliases: bool = True

    # Edge filtering
    min_similarity: float = 0.0
    top_k_skills: int = 0  # 0 = all skills
    buckets: List[str] = field(default_factory=list)  # empty = all buckets

    # Column mappings
    skills_column: str = "importance_standardised"
    category_column: str = "Assigned_Occupation_Group"
    fallback_category_column: str = "Group"
    job_id_column: str = "auto"

    # Processing options
    chunk_size: int = 10000
    verbose: bool = False

    # Sampling options
    subset: bool = False
    subset_mode: str = "perf"  # "stats" or "perf"

    # Statistical sampling options (subset_mode = "stats")
    conf_level: float = 0.95
    margin_error: float = 0.03
    p_worstcase: bool = True
    p_estimate: float = 0.5
    finite_correction: bool = True
    min_per_category: int = 30
    mean_target_column: Optional[str] = None
    mean_margin_error: float = 2000.0
    pilot_n: Optional[int] = None

    # Performance sampling options (subset_mode = "perf")
    subset_max_bytes: int = 100_000_000  # 100MB
    subset_seed: int = 42
    subset_categories: int = 0  # 0 = all categories
    category_list: Optional[List[str]] = None

    @classmethod
    def from_args(cls, args: Optional[List[str]] = None) -> 'Config':
        """Create Config from command-line arguments."""
        parser = argparse.ArgumentParser(
            description="Job-Skills Graph Builder v2.0",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Full graph export
  python build_graph.py --input data.csv --outdir ./output

  # Lightweight Gephi export
  python build_graph.py --input data.csv --outdir ./output \\
    --min_similarity 0.6 --top_k_skills 10

  # Statistical sample for research
  python build_graph.py --input data.csv --outdir ./output \\
    --subset --subset_mode stats --conf_level 0.95 --margin_error 0.03

  # Performance sample for Gephi
  python build_graph.py --input data.csv --outdir ./output \\
    --subset --subset_mode perf --subset_max_bytes 100000000
            """
        )

        # Required arguments
        parser.add_argument(
            '--input', '-i',
            required=True,
            help='Input CSV or Excel file path'
        )
        parser.add_argument(
            '--outdir', '-o',
            default='./output',
            help='Output directory (default: ./output)'
        )

        # Output format options
        parser.add_argument(
            '--format', '-f',
            default='csv,graphml',
            help='Output formats, comma-separated (default: csv,graphml)'
        )
        parser.add_argument(
            '--drop_thinking',
            type=lambda x: x.lower() == 'true',
            default=True,
            help='Omit "thinking" field from edges (default: true)'
        )
        parser.add_argument(
            '--include_aliases',
            type=lambda x: x.lower() == 'true',
            default=True,
            help='Include skill aliases in output (default: true)'
        )

        # Edge filtering
        parser.add_argument(
            '--min_similarity',
            type=float,
            default=0.0,
            help='Minimum mapping_similarity threshold (default: 0.0)'
        )
        parser.add_argument(
            '--top_k_skills',
            type=int,
            default=0,
            help='Max skills per job, 0 for all (default: 0)'
        )
        parser.add_argument(
            '--buckets',
            default='',
            help='Filter by bucket, comma-separated or empty for all'
        )

        # Column mappings
        parser.add_argument(
            '--skills_column',
            default='importance_standardised',
            help='Column name containing skills JSON'
        )
        parser.add_argument(
            '--category_column',
            default='Assigned_Occupation_Group',
            help='Column name for categories'
        )
        parser.add_argument(
            '--job_id_column',
            default='auto',
            help='Column name for job ID, or "auto" to generate'
        )

        # Processing options
        parser.add_argument(
            '--chunk_size',
            type=int,
            default=10000,
            help='Rows per chunk for streaming (default: 10000)'
        )
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Enable verbose logging'
        )

        # Sampling options
        parser.add_argument(
            '--subset',
            action='store_true',
            help='Enable subset sampling'
        )
        parser.add_argument(
            '--subset_mode',
            choices=['stats', 'perf'],
            default='perf',
            help='Sampling mode: stats or perf (default: perf)'
        )

        # Statistical sampling options
        parser.add_argument(
            '--conf_level',
            type=float,
            default=0.95,
            help='Confidence level for stats mode (default: 0.95)'
        )
        parser.add_argument(
            '--margin_error',
            type=float,
            default=0.03,
            help='Margin of error for proportions (default: 0.03)'
        )
        parser.add_argument(
            '--p_worstcase',
            type=lambda x: x.lower() == 'true',
            default=True,
            help='Use p=0.5 for worst-case variance (default: true)'
        )
        parser.add_argument(
            '--p_estimate',
            type=float,
            default=0.5,
            help='Estimated proportion if not worst-case (default: 0.5)'
        )
        parser.add_argument(
            '--finite_correction',
            type=lambda x: x.lower() == 'true',
            default=True,
            help='Apply finite population correction (default: true)'
        )
        parser.add_argument(
            '--min_per_category',
            type=int,
            default=30,
            help='Minimum samples per category (default: 30)'
        )
        parser.add_argument(
            '--mean_target_column',
            default=None,
            help='Column for mean estimation (e.g., salary_mean_inr_month)'
        )
        parser.add_argument(
            '--mean_margin_error',
            type=float,
            default=2000.0,
            help='Absolute error for mean estimation (default: 2000)'
        )

        # Performance sampling options
        parser.add_argument(
            '--subset_max_bytes',
            type=int,
            default=100_000_000,
            help='Target file size in bytes (default: 100000000)'
        )
        parser.add_argument(
            '--subset_seed',
            type=int,
            default=42,
            help='Random seed for reproducibility (default: 42)'
        )
        parser.add_argument(
            '--subset_categories',
            type=int,
            default=0,
            help='Limit to top N categories, 0 for all (default: 0)'
        )
        parser.add_argument(
            '--category_list',
            default=None,
            help='Specific categories, comma-separated'
        )

        parsed = parser.parse_args(args)

        # Convert to Config
        config = cls(
            input_path=parsed.input,
            output_dir=parsed.outdir,
            formats=[f.strip() for f in parsed.format.split(',')],
            drop_thinking=parsed.drop_thinking,
            include_aliases=parsed.include_aliases,
            min_similarity=parsed.min_similarity,
            top_k_skills=parsed.top_k_skills,
            buckets=[b.strip() for b in parsed.buckets.split(',') if b.strip()],
            skills_column=parsed.skills_column,
            category_column=parsed.category_column,
            job_id_column=parsed.job_id_column,
            chunk_size=parsed.chunk_size,
            verbose=parsed.verbose,
            subset=parsed.subset,
            subset_mode=parsed.subset_mode,
            conf_level=parsed.conf_level,
            margin_error=parsed.margin_error,
            p_worstcase=parsed.p_worstcase,
            p_estimate=parsed.p_estimate,
            finite_correction=parsed.finite_correction,
            min_per_category=parsed.min_per_category,
            mean_target_column=parsed.mean_target_column,
            mean_margin_error=parsed.mean_margin_error,
            subset_max_bytes=parsed.subset_max_bytes,
            subset_seed=parsed.subset_seed,
            subset_categories=parsed.subset_categories,
            category_list=[c.strip() for c in parsed.category_list.split(',')] if parsed.category_list else None
        )

        return config

    def validate(self) -> List[str]:
        """
        Validate configuration.

        Returns list of error messages (empty if valid).
        """
        errors = []

        # Check input file exists
        if not os.path.exists(self.input_path):
            errors.append(f"Input file not found: {self.input_path}")

        # Check input file extension
        ext = os.path.splitext(self.input_path)[1].lower()
        if ext not in ['.csv', '.xlsx', '.xls']:
            errors.append(f"Unsupported input format: {ext}. Use .csv, .xlsx, or .xls")

        # Validate formats
        valid_formats = ['csv', 'graphml']
        for fmt in self.formats:
            if fmt not in valid_formats:
                errors.append(f"Invalid format: {fmt}. Use: {valid_formats}")

        # Validate ranges
        if not (0.0 <= self.min_similarity <= 1.0):
            errors.append(f"min_similarity must be 0.0-1.0, got {self.min_similarity}")

        if self.top_k_skills < 0:
            errors.append(f"top_k_skills must be >= 0, got {self.top_k_skills}")

        if not (0.80 <= self.conf_level <= 0.999):
            errors.append(f"conf_level must be 0.80-0.999, got {self.conf_level}")

        if not (0.001 <= self.margin_error <= 0.5):
            errors.append(f"margin_error must be 0.001-0.5, got {self.margin_error}")

        return errors

    def to_dict(self) -> dict:
        """Convert config to dictionary for report.json."""
        return {
            'input_path': self.input_path,
            'output_dir': self.output_dir,
            'formats': self.formats,
            'drop_thinking': self.drop_thinking,
            'min_similarity': self.min_similarity,
            'top_k_skills': self.top_k_skills,
            'subset': self.subset,
            'subset_mode': self.subset_mode if self.subset else None,
            'conf_level': self.conf_level if self.subset and self.subset_mode == 'stats' else None,
            'margin_error': self.margin_error if self.subset and self.subset_mode == 'stats' else None,
            'subset_max_bytes': self.subset_max_bytes if self.subset and self.subset_mode == 'perf' else None,
            'subset_seed': self.subset_seed if self.subset else None
        }
