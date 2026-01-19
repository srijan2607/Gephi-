#!/usr/bin/env python3
"""
Job-Skills Graph Builder v2.0

Build a knowledge graph from job posting data with:
- Canonicalized skills for proper overlap
- Full job metadata in exports
- Statistical and performance sampling
- Gephi-ready GraphML output

Usage:
    python build_graph.py --input data.csv --outdir ./output

    # With sampling for Gephi
    python build_graph.py --input data.csv --outdir ./output \\
        --subset --subset_mode perf --subset_max_bytes 100000000

    # Statistical sample for research
    python build_graph.py --input data.csv --outdir ./output \\
        --subset --subset_mode stats --conf_level 0.95 --margin_error 0.03
"""

import sys
import os
import logging
from typing import Optional

# Add package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graph_builder.config import Config
from graph_builder.parser import DataParser
from graph_builder.normalizer import SkillNormalizer
from graph_builder.graph import GraphBuilder
from graph_builder.sampler import get_sampler
from graph_builder.exporter import Exporter
from graph_builder.validator import Validator
from graph_builder.utils import setup_logging


def main(args: Optional[list] = None) -> int:
    """
    Main entry point for the graph builder.

    Args:
        args: Command line arguments (uses sys.argv if None)

    Returns:
        Exit code (0 for success)
    """
    # Parse configuration
    try:
        config = Config.from_args(args)
    except SystemExit:
        return 1

    # Setup logging
    logger = setup_logging(config.verbose)
    logger.info("Job-Skills Graph Builder v2.0")
    logger.info(f"Input: {config.input_path}")
    logger.info(f"Output: {config.output_dir}")

    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(error)
        return 1

    try:
        # Phase 1: Parse input data
        logger.info("=" * 50)
        logger.info("PHASE 1: Parsing input data")
        logger.info("=" * 50)

        parser = DataParser(config)
        data = list(parser.parse())  # Collect all rows

        if not data:
            logger.error("No data parsed from input file")
            return 1

        logger.info(f"Parsed {len(data):,} rows")

        # Phase 2: Normalize skills
        logger.info("=" * 50)
        logger.info("PHASE 2: Normalizing skills")
        logger.info("=" * 50)

        normalizer = SkillNormalizer()
        data = normalizer.process_all(data)

        # Phase 3: Build graph
        logger.info("=" * 50)
        logger.info("PHASE 3: Building graph")
        logger.info("=" * 50)

        builder = GraphBuilder(config)
        graph = builder.build(data, normalizer)

        # Phase 4: Sample (if requested)
        sampling_report = None
        if config.subset:
            logger.info("=" * 50)
            logger.info(f"PHASE 4: Sampling ({config.subset_mode} mode)")
            logger.info("=" * 50)

            sampler = get_sampler(config.subset_mode)
            graph = sampler.sample(graph, config)
            sampling_report = sampler.report

        # Phase 5: Export
        logger.info("=" * 50)
        logger.info("PHASE 5: Exporting outputs")
        logger.info("=" * 50)

        exporter = Exporter(config)
        output_files = exporter.export(graph, normalizer, parser)

        # Phase 6: Validate and report
        logger.info("=" * 50)
        logger.info("PHASE 6: Validating and reporting")
        logger.info("=" * 50)

        validator = Validator(config)
        report = validator.validate(
            graph, normalizer, parser, output_files, sampling_report
        )
        validator.write_report(report)

        # Print summary
        validator.print_summary(report)

        # Check for errors
        if report.get('errors'):
            logger.error("Build completed with errors")
            return 1

        logger.info("Build completed successfully!")
        return 0

    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Build failed: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
