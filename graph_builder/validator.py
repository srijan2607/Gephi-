"""
Validation and reporting module.

Performs quality checks and generates report.json with metrics.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from collections import Counter

from .config import Config
from .graph import GraphBuilder
from .normalizer import SkillNormalizer
from .parser import DataParser
from .utils import get_timestamp, format_bytes


logger = logging.getLogger('graph_builder')


class Validator:
    """Validate graph quality and generate reports."""

    def __init__(self, config: Config):
        self.config = config
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def validate(
        self,
        graph: GraphBuilder,
        normalizer: SkillNormalizer,
        parser: DataParser,
        output_files: Dict[str, str],
        sampling_report: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Validate the graph and generate a comprehensive report.

        Args:
            graph: Built graph
            normalizer: Skill normalizer
            parser: Data parser
            output_files: Dict of output file paths
            sampling_report: Optional sampling report from sampler

        Returns:
            Complete report dict
        """
        logger.info("Validating graph...")

        # Build report
        report = {
            'meta': self._get_meta(),
            'config': self.config.to_dict(),
            'input': self._get_input_stats(parser),
            'normalization': normalizer.get_stats(),
            'graph': graph.get_stats(),
            'quality': self._check_quality(graph, parser),
            'output_files': self._get_output_stats(output_files),
            'sampling': sampling_report,
            'warnings': self.warnings,
            'errors': self.errors
        }

        # Run assertions
        self._run_assertions(report)

        return report

    def write_report(self, report: Dict[str, Any]) -> str:
        """Write report to JSON file."""
        path = os.path.join(self.config.output_dir, 'report.json')

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Report written to {path}")
        return path

    def _get_meta(self) -> Dict[str, Any]:
        """Get metadata for report."""
        return {
            'version': '2.0.0',
            'timestamp': get_timestamp(),
            'input_file': self.config.input_path,
            'output_dir': self.config.output_dir
        }

    def _get_input_stats(self, parser: DataParser) -> Dict[str, Any]:
        """Get input file statistics."""
        return {
            'rows_total': parser.total_rows,
            'rows_parsed': parser.parsed_rows,
            'rows_failed': len(parser.bad_rows),
            'columns': parser.columns
        }

    def _check_quality(
        self,
        graph: GraphBuilder,
        parser: DataParser
    ) -> Dict[str, Any]:
        """Check graph quality metrics."""
        jobs = [n for n in graph.nodes.values() if n['kind'] == 'job']
        skills = [n for n in graph.nodes.values() if n['kind'] == 'skill']

        # Jobs with skills
        jobs_with_skills_pct = (
            len(graph.jobs_with_skills) / len(jobs) * 100
            if jobs else 0
        )

        # Jobs with category
        jobs_with_category_pct = (
            len(graph.jobs_with_category) / len(jobs) * 100
            if jobs else 0
        )

        # Average skills per job
        skill_edges = [e for e in graph.edges if e['rel'] == 'REQUIRES_SKILL']
        avg_skills = len(skill_edges) / len(jobs) if jobs else 0

        # Metadata coverage
        coverage = self._check_metadata_coverage(jobs)

        # Top skills
        skill_edge_counts = Counter()
        for edge in graph.edges:
            if edge['rel'] == 'REQUIRES_SKILL':
                skill_edge_counts[edge['target']] += 1

        top_skills = []
        for skill_id, count in skill_edge_counts.most_common(10):
            if skill_id in graph.nodes:
                top_skills.append({
                    'skill': graph.nodes[skill_id].get('label', skill_id),
                    'job_count': count
                })

        return {
            'jobs_with_skills_pct': round(jobs_with_skills_pct, 2),
            'jobs_with_category_pct': round(jobs_with_category_pct, 2),
            'avg_skills_per_job': round(avg_skills, 2),
            'bad_rows_count': len(parser.bad_rows),
            'metadata_coverage': coverage,
            'top_skills': top_skills
        }

    def _check_metadata_coverage(self, jobs: List[Dict]) -> Dict[str, float]:
        """Check coverage of metadata fields in job nodes."""
        if not jobs:
            return {}

        fields = [
            'job_title', 'company_name', 'district', 'nco_code',
            'salary_mean_inr_month', 'schedule_type', 'posted_at',
            'work_from_home', 'assigned_occupation_group'
        ]

        coverage = {}
        for field in fields:
            non_empty = sum(
                1 for j in jobs
                if j.get(field) and str(j.get(field)).strip() and j.get(field) != 0
            )
            coverage[field] = round(non_empty / len(jobs) * 100, 1)

        return coverage

    def _get_output_stats(self, output_files: Dict[str, str]) -> Dict[str, Dict]:
        """Get statistics for output files."""
        stats = {}

        for name, path in output_files.items():
            if os.path.exists(path):
                size = os.path.getsize(path)
                stats[name] = {
                    'path': path,
                    'size_bytes': size,
                    'size_human': format_bytes(size)
                }

                # Count rows for CSV files
                if path.endswith('.csv'):
                    try:
                        with open(path, 'r') as f:
                            # Count lines (minus header)
                            row_count = sum(1 for _ in f) - 1
                            stats[name]['rows'] = max(0, row_count)
                    except Exception:
                        pass
            else:
                stats[name] = {
                    'path': path,
                    'error': 'File not found'
                }

        return stats

    def _run_assertions(self, report: Dict[str, Any]):
        """Run quality assertions and log warnings/errors."""
        quality = report['quality']

        # Check jobs with skills
        if quality['jobs_with_skills_pct'] < 95:
            self.warnings.append(
                f"Only {quality['jobs_with_skills_pct']:.1f}% of jobs have skill edges "
                f"(target: >95%)"
            )

        if quality['jobs_with_skills_pct'] < 80:
            self.errors.append(
                f"Critical: Only {quality['jobs_with_skills_pct']:.1f}% of jobs have skill edges"
            )

        # Check deduplication
        norm = report['normalization']
        if norm['dedup_ratio'] < 0.5:
            self.warnings.append(
                f"Skill deduplication ratio is only {norm['dedup_ratio']:.1%} "
                f"(expected >50%)"
            )

        # Check average skills per job
        if quality['avg_skills_per_job'] < 3:
            self.warnings.append(
                f"Average skills per job is low: {quality['avg_skills_per_job']:.1f} "
                f"(expected 5-15)"
            )

        # Check bad rows
        input_stats = report['input']
        if input_stats['rows_failed'] > 0:
            fail_pct = input_stats['rows_failed'] / input_stats['rows_total'] * 100
            if fail_pct > 5:
                self.warnings.append(
                    f"{input_stats['rows_failed']:,} rows failed to parse "
                    f"({fail_pct:.1f}%) - see bad_rows.csv"
                )
            else:
                logger.info(
                    f"{input_stats['rows_failed']:,} rows failed to parse - see bad_rows.csv"
                )

        # Check metadata coverage
        coverage = quality.get('metadata_coverage', {})
        low_coverage_fields = [
            field for field, pct in coverage.items()
            if pct < 50 and field not in ['salary_mean_inr_month', 'work_from_home', 'posted_at']
        ]
        if low_coverage_fields:
            self.warnings.append(
                f"Low metadata coverage for: {', '.join(low_coverage_fields)}"
            )

        # Log summary
        if self.errors:
            for error in self.errors:
                logger.error(error)
        if self.warnings:
            for warning in self.warnings:
                logger.warning(warning)

        if not self.errors and not self.warnings:
            logger.info("All quality checks passed!")

    def print_summary(self, report: Dict[str, Any]):
        """Print a human-readable summary."""
        print("\n" + "=" * 60)
        print("GRAPH BUILDER REPORT")
        print("=" * 60)

        # Input summary
        inp = report['input']
        print(f"\nInput: {inp['rows_parsed']:,} rows parsed "
              f"({inp['rows_failed']:,} failed)")

        # Normalization summary
        norm = report['normalization']
        print(f"\nSkill Normalization:")
        print(f"  Raw strings: {norm['raw_skill_strings']:,}")
        print(f"  Canonical skills: {norm['canonical_skills']:,}")
        print(f"  Deduplication: {norm['dedup_ratio']:.1%}")

        # Graph summary
        graph = report['graph']
        print(f"\nGraph:")
        print(f"  Nodes: {graph['nodes_total']:,}")
        print(f"    Jobs: {graph['nodes_by_kind']['job']:,}")
        print(f"    Skills: {graph['nodes_by_kind']['skill']:,}")
        print(f"    Categories: {graph['nodes_by_kind']['category']:,}")
        print(f"  Edges: {graph['edges_total']:,}")
        print(f"    Job→Skill: {graph['edges_by_rel']['REQUIRES_SKILL']:,}")
        print(f"    Job→Category: {graph['edges_by_rel']['IN_CATEGORY']:,}")

        # Quality summary
        quality = report['quality']
        print(f"\nQuality:")
        print(f"  Jobs with skills: {quality['jobs_with_skills_pct']:.1f}%")
        print(f"  Avg skills/job: {quality['avg_skills_per_job']:.1f}")

        # Output files
        print(f"\nOutput files:")
        for name, stats in report['output_files'].items():
            if 'size_human' in stats:
                print(f"  {name}: {stats['size_human']}")

        # Warnings
        if report['warnings']:
            print(f"\nWarnings ({len(report['warnings'])}):")
            for w in report['warnings']:
                print(f"  - {w}")

        print("\n" + "=" * 60)
