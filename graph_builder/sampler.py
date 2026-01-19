"""
Sampling module for creating representative or size-bounded subsets.

Two modes:
1. Statistical sampling (stats): Cochran's formula with stratification
2. Performance sampling (perf): Size-bounded for Gephi usability
"""

import random
import logging
import math
from typing import Dict, List, Any, Set, Optional, Tuple
from collections import defaultdict, Counter
from abc import ABC, abstractmethod

import numpy as np

from .config import Config
from .graph import GraphBuilder
from .utils import z_score


logger = logging.getLogger('graph_builder')


class BaseSampler(ABC):
    """Base class for graph samplers."""

    @abstractmethod
    def sample(self, graph: GraphBuilder, config: Config) -> GraphBuilder:
        """Sample the graph and return a new subgraph."""
        pass

    def _build_subgraph(
        self,
        original: GraphBuilder,
        sampled_job_ids: Set[str]
    ) -> GraphBuilder:
        """
        Build a subgraph containing only sampled jobs and their connections.

        Preserves graph integrity:
        - All skills connected to sampled jobs
        - All categories connected to sampled jobs
        """
        # Create new graph builder with same config
        subgraph = GraphBuilder(original.config)

        # Copy sampled job nodes
        for job_id in sampled_job_ids:
            if job_id in original.nodes:
                subgraph.nodes[job_id] = original.nodes[job_id].copy()

        # Find connected skills and categories
        connected_skills: Set[str] = set()
        connected_categories: Set[str] = set()

        for edge in original.edges:
            if edge['source'] in sampled_job_ids:
                if edge['rel'] == 'REQUIRES_SKILL':
                    connected_skills.add(edge['target'])
                    subgraph.edges.append(edge.copy())
                elif edge['rel'] == 'IN_CATEGORY':
                    connected_categories.add(edge['target'])
                    subgraph.edges.append(edge.copy())

        # Add skill nodes
        for skill_id in connected_skills:
            if skill_id in original.nodes:
                subgraph.nodes[skill_id] = original.nodes[skill_id].copy()

        # Add category nodes
        for cat_id in connected_categories:
            if cat_id in original.nodes:
                subgraph.nodes[cat_id] = original.nodes[cat_id].copy()

        # Update tracking sets
        subgraph.jobs_with_skills = sampled_job_ids & original.jobs_with_skills
        subgraph.jobs_with_category = sampled_job_ids & original.jobs_with_category
        subgraph.categories_seen = connected_categories

        logger.info(
            f"Subgraph created: {len(subgraph.nodes):,} nodes, "
            f"{len(subgraph.edges):,} edges"
        )

        return subgraph


class StatisticalSampler(BaseSampler):
    """
    Statistical sampling using Cochran's formula with stratification.

    For proportion estimation (default):
        n₀ = (Z² × p × (1-p)) / e²

    With finite population correction:
        n = n₀ / (1 + (n₀ - 1) / N)

    Stratified by category with proportional allocation.
    """

    def __init__(self):
        self.report: Dict[str, Any] = {}

    def sample(self, graph: GraphBuilder, config: Config) -> GraphBuilder:
        """
        Create a statistically valid sample.

        Args:
            graph: Original graph
            config: Configuration with sampling parameters

        Returns:
            Subgraph with sampled jobs
        """
        random.seed(config.subset_seed)
        np.random.seed(config.subset_seed)

        # Get all jobs
        jobs = {
            node_id: node
            for node_id, node in graph.nodes.items()
            if node['kind'] == 'job'
        }
        N = len(jobs)

        logger.info(f"Statistical sampling from {N:,} jobs")

        # Calculate sample size
        n = self._calculate_sample_size(N, config)
        logger.info(f"Target sample size: {n:,} (using Cochran's formula)")

        # Stratify by category
        strata = self._stratify_jobs(jobs, graph)
        logger.info(f"Found {len(strata):,} categories for stratification")

        # Allocate samples per stratum
        allocation = self._allocate_proportional(strata, n, config)

        # Sample from each stratum
        sampled_job_ids = self._sample_strata(strata, allocation, config)
        logger.info(f"Sampled {len(sampled_job_ids):,} jobs")

        # Build report
        self.report = self._build_report(N, n, config, strata, allocation, sampled_job_ids)

        # Build subgraph
        return self._build_subgraph(graph, sampled_job_ids)

    def _calculate_sample_size(self, N: int, config: Config) -> int:
        """
        Calculate required sample size using Cochran's formula.

        For proportions:
            n₀ = (Z² × p × (1-p)) / e²

        For means (if mean_target_column specified):
            n₀ = (Z × σ / e)²
            (requires pilot sample for σ estimation)
        """
        Z = z_score(config.conf_level)
        e = config.margin_error

        # Default: proportion estimation (worst-case)
        p = 0.5 if config.p_worstcase else config.p_estimate

        # Cochran's formula for proportions
        n0 = (Z ** 2 * p * (1 - p)) / (e ** 2)

        # Finite population correction
        if config.finite_correction and N > 0:
            n = n0 / (1 + (n0 - 1) / N)
        else:
            n = n0

        # Store formula in report
        self._formula_details = {
            'method': 'cochran_proportion',
            'Z': round(Z, 4),
            'p': p,
            'e': e,
            'n0': round(n0, 2),
            'N': N,
            'finite_correction': config.finite_correction,
            'n_final': int(math.ceil(n))
        }

        return int(math.ceil(n))

    def _stratify_jobs(
        self,
        jobs: Dict[str, Dict],
        graph: GraphBuilder
    ) -> Dict[str, List[str]]:
        """
        Group jobs by category.

        Returns:
            Dict mapping category_id to list of job_ids
        """
        strata: Dict[str, List[str]] = defaultdict(list)

        # Build job -> category mapping from edges
        job_category = {}
        for edge in graph.edges:
            if edge['rel'] == 'IN_CATEGORY':
                job_category[edge['source']] = edge['target']

        # Group by category
        for job_id in jobs:
            cat_id = job_category.get(job_id, 'uncategorized')
            strata[cat_id].append(job_id)

        return dict(strata)

    def _allocate_proportional(
        self,
        strata: Dict[str, List[str]],
        n: int,
        config: Config
    ) -> Dict[str, int]:
        """
        Allocate sample sizes to strata proportionally.

        n_h = n × (N_h / N)

        With minimum per stratum constraint.
        """
        N = sum(len(jobs) for jobs in strata.values())
        allocation: Dict[str, int] = {}

        # First pass: proportional allocation
        for cat_id, jobs in strata.items():
            N_h = len(jobs)
            n_h = int(math.ceil(n * (N_h / N)))
            allocation[cat_id] = n_h

        # Second pass: enforce minimum
        min_per = config.min_per_category
        warnings = []

        for cat_id, jobs in strata.items():
            N_h = len(jobs)

            if N_h < min_per:
                # Can't meet minimum - take all
                allocation[cat_id] = N_h
                warnings.append(
                    f"Category '{cat_id}' has only {N_h} jobs "
                    f"(below min_per_category={min_per})"
                )
            else:
                allocation[cat_id] = max(allocation[cat_id], min_per)

        # Adjust if total exceeds n
        total_allocated = sum(allocation.values())
        if total_allocated > n * 1.5:
            logger.warning(
                f"Allocation ({total_allocated:,}) exceeds target ({n:,}) "
                f"due to minimum constraints"
            )

        self._allocation_warnings = warnings
        return allocation

    def _sample_strata(
        self,
        strata: Dict[str, List[str]],
        allocation: Dict[str, int],
        config: Config
    ) -> Set[str]:
        """Sample from each stratum according to allocation."""
        sampled: Set[str] = set()

        for cat_id, jobs in strata.items():
            n_h = allocation.get(cat_id, 0)
            n_h = min(n_h, len(jobs))  # Can't sample more than exists

            if n_h > 0:
                selected = random.sample(jobs, n_h)
                sampled.update(selected)

        return sampled

    def _build_report(
        self,
        N: int,
        n: int,
        config: Config,
        strata: Dict[str, List[str]],
        allocation: Dict[str, int],
        sampled: Set[str]
    ) -> Dict[str, Any]:
        """Build the sampling report."""
        return {
            'sampling_mode': 'stats',
            'population': {
                'total_jobs': N,
                'total_categories': len(strata)
            },
            'parameters': {
                'confidence_level': config.conf_level,
                'margin_of_error': config.margin_error,
                'p_estimate': 0.5 if config.p_worstcase else config.p_estimate,
                'p_worstcase': config.p_worstcase,
                'finite_correction': config.finite_correction,
                'min_per_category': config.min_per_category,
                'seed': config.subset_seed
            },
            'formulas': self._formula_details,
            'sample': {
                'target_n': n,
                'actual_n': len(sampled)
            },
            'stratification': {
                cat_id: {
                    'population': len(strata[cat_id]),
                    'allocated': allocation.get(cat_id, 0),
                    'sampled': sum(1 for j in sampled if j in strata[cat_id])
                }
                for cat_id in strata
            },
            'warnings': getattr(self, '_allocation_warnings', [])
        }


class PerformanceSampler(BaseSampler):
    """
    Performance sampling bounded by file size.

    Targets a specific output size (e.g., 100MB) for Gephi usability.
    Not statistically valid, but produces a usable subset.
    """

    def __init__(self):
        self.report: Dict[str, Any] = {}

    def sample(self, graph: GraphBuilder, config: Config) -> GraphBuilder:
        """
        Create a size-bounded sample.

        Args:
            graph: Original graph
            config: Configuration with size parameters

        Returns:
            Subgraph within size bounds
        """
        random.seed(config.subset_seed)

        # Get all jobs
        jobs = {
            node_id: node
            for node_id, node in graph.nodes.items()
            if node['kind'] == 'job'
        }

        logger.info(
            f"Performance sampling targeting {config.subset_max_bytes / 1_000_000:.0f}MB"
        )

        # Select categories
        categories = self._select_categories(graph, config)
        logger.info(f"Selected {len(categories):,} categories")

        # Get jobs in selected categories
        eligible_jobs = self._get_jobs_in_categories(jobs, graph, categories)
        logger.info(f"Eligible jobs: {len(eligible_jobs):,}")

        # Estimate max jobs for target size
        max_jobs = self._estimate_max_jobs(config)
        logger.info(f"Estimated max jobs for size target: {max_jobs:,}")

        # Sample jobs
        sampled_job_ids = self._sample_within_budget(
            eligible_jobs, graph, max_jobs, config
        )
        logger.info(f"Sampled {len(sampled_job_ids):,} jobs")

        # Build report
        self.report = self._build_report(config, categories, eligible_jobs, sampled_job_ids)

        # Build subgraph
        return self._build_subgraph(graph, sampled_job_ids)

    def _select_categories(
        self,
        graph: GraphBuilder,
        config: Config
    ) -> Set[str]:
        """Select categories to include."""
        if config.category_list:
            # User-specified categories
            return set(f"cat:{c}" for c in config.category_list)

        # Get all categories with job counts
        cat_counts: Counter = Counter()
        for edge in graph.edges:
            if edge['rel'] == 'IN_CATEGORY':
                cat_counts[edge['target']] += 1

        if config.subset_categories > 0:
            # Top N categories by job count
            top_cats = cat_counts.most_common(config.subset_categories)
            return set(cat_id for cat_id, _ in top_cats)

        # All categories
        return set(cat_counts.keys())

    def _get_jobs_in_categories(
        self,
        jobs: Dict[str, Dict],
        graph: GraphBuilder,
        categories: Set[str]
    ) -> List[str]:
        """Get jobs that belong to selected categories."""
        # Build job -> category mapping
        job_category = {}
        for edge in graph.edges:
            if edge['rel'] == 'IN_CATEGORY':
                job_category[edge['source']] = edge['target']

        eligible = [
            job_id
            for job_id in jobs
            if job_category.get(job_id) in categories
        ]

        return eligible

    def _estimate_max_jobs(self, config: Config) -> int:
        """
        Estimate maximum jobs that fit within size budget.

        Rough estimation based on typical sizes:
        - Job node: ~500 bytes
        - Skill edge: ~150 bytes (without thinking)
        - Avg 8 skills per job
        - Skill node: ~100 bytes (amortized)
        """
        bytes_per_job = 500  # Job node
        bytes_per_job += 100  # Category edge

        avg_skills = config.top_k_skills if config.top_k_skills > 0 else 8
        bytes_per_job += avg_skills * 150  # Skill edges
        bytes_per_job += avg_skills * 20   # Skill nodes (amortized)

        # Safety margin (80%)
        max_jobs = int(config.subset_max_bytes / bytes_per_job * 0.8)

        return max(max_jobs, 100)  # At least 100 jobs

    def _sample_within_budget(
        self,
        eligible_jobs: List[str],
        graph: GraphBuilder,
        max_jobs: int,
        config: Config
    ) -> Set[str]:
        """Sample jobs within budget, stratified by category."""
        if len(eligible_jobs) <= max_jobs:
            return set(eligible_jobs)

        # Stratify for balanced sampling
        job_category = {}
        for edge in graph.edges:
            if edge['rel'] == 'IN_CATEGORY':
                job_category[edge['source']] = edge['target']

        strata: Dict[str, List[str]] = defaultdict(list)
        for job_id in eligible_jobs:
            cat_id = job_category.get(job_id, 'uncategorized')
            strata[cat_id].append(job_id)

        # Proportional allocation
        sampled: Set[str] = set()
        N = len(eligible_jobs)

        for cat_id, jobs in strata.items():
            proportion = len(jobs) / N
            n_h = max(1, int(max_jobs * proportion))
            n_h = min(n_h, len(jobs))

            selected = random.sample(jobs, n_h)
            sampled.update(selected)

            if len(sampled) >= max_jobs:
                break

        return sampled

    def _build_report(
        self,
        config: Config,
        categories: Set[str],
        eligible_jobs: List[str],
        sampled: Set[str]
    ) -> Dict[str, Any]:
        """Build the sampling report."""
        return {
            'sampling_mode': 'perf',
            'constraints': {
                'max_bytes': config.subset_max_bytes,
                'top_k_skills_per_job': config.top_k_skills,
                'min_similarity': config.min_similarity,
                'drop_thinking': config.drop_thinking,
                'num_categories': len(categories),
                'seed': config.subset_seed
            },
            'result': {
                'eligible_jobs': len(eligible_jobs),
                'jobs_sampled': len(sampled),
                'categories_included': len(categories)
            }
        }


def get_sampler(mode: str) -> BaseSampler:
    """Factory function to get the appropriate sampler."""
    if mode == 'stats':
        return StatisticalSampler()
    elif mode == 'perf':
        return PerformanceSampler()
    else:
        raise ValueError(f"Unknown sampling mode: {mode}")
