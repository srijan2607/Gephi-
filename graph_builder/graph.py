"""
Graph construction module.

Builds the knowledge graph with:
- Job nodes (with full metadata)
- Skill nodes (canonicalized)
- Category nodes
- Edges: Job→Skill, Job→Category
"""

import logging
from typing import Dict, List, Any, Set, Optional
from collections import defaultdict

from .utils import slugify, safe_float
from .normalizer import SkillNormalizer
from .config import Config


logger = logging.getLogger('graph_builder')


class GraphBuilder:
    """
    Build the job-skills knowledge graph.

    Node types:
    - job: Individual job postings with full metadata
    - skill: Canonicalized skills
    - category: Occupation groups/categories

    Edge types:
    - REQUIRES_SKILL: Job → Skill
    - IN_CATEGORY: Job → Category
    """

    def __init__(self, config: Config):
        self.config = config

        # Graph storage
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []

        # Tracking
        self.categories_seen: Set[str] = set()
        self.jobs_with_skills: Set[str] = set()
        self.jobs_with_category: Set[str] = set()

        # Stats
        self.skill_edges_created = 0
        self.category_edges_created = 0
        self.skills_filtered_similarity = 0
        self.skills_filtered_bucket = 0

    def build(self, data: List[Dict], normalizer: SkillNormalizer) -> 'GraphBuilder':
        """
        Build the complete graph from parsed data.

        Args:
            data: List of parsed row dicts
            normalizer: SkillNormalizer with populated dictionary

        Returns:
            self (for chaining)
        """
        logger.info("Building graph...")

        for row in data:
            self._process_row(row, normalizer)

        # Add skill nodes from normalizer dictionary
        self._add_skill_nodes(normalizer)

        # Update category job counts
        self._update_category_counts()

        logger.info(
            f"Graph built: {len(self.nodes):,} nodes, {len(self.edges):,} edges"
        )
        logger.info(
            f"  Jobs: {self._count_by_kind('job'):,}, "
            f"Skills: {self._count_by_kind('skill'):,}, "
            f"Categories: {self._count_by_kind('category'):,}"
        )
        logger.info(
            f"  Job→Skill edges: {self.skill_edges_created:,}, "
            f"Job→Category edges: {self.category_edges_created:,}"
        )

        if self.skills_filtered_similarity > 0:
            logger.info(
                f"  Filtered {self.skills_filtered_similarity:,} skill edges "
                f"by min_similarity < {self.config.min_similarity}"
            )

        return self

    def _process_row(self, row: Dict, normalizer: SkillNormalizer):
        """Process a single job row."""
        # Create job node
        job_id = f"job:{row['job_id']}"
        self.nodes[job_id] = self._create_job_node(row)

        # Create/reference category node and edge
        category_id = self._ensure_category(row)
        if category_id:
            self.edges.append({
                'source': job_id,
                'target': category_id,
                'rel': 'IN_CATEGORY'
            })
            self.jobs_with_category.add(job_id)
            self.category_edges_created += 1

        # Create skill edges
        self._create_skill_edges(job_id, row, normalizer)

    def _create_job_node(self, row: Dict) -> Dict[str, Any]:
        """Create a job node with full metadata."""
        return {
            'id': f"job:{row['job_id']}",
            'label': row['job_title'] or 'Untitled Job',
            'kind': 'job',

            # Core metadata
            'job_title': row['job_title'],
            'company_name': row['company_name'],
            'posted_at': row['posted_at'],

            # Work arrangement
            'schedule_type': row['schedule_type'],
            'work_from_home': row['work_from_home'],
            'district': row['district'],

            # Classification
            'nco_code': row['nco_code'],
            'group_name': row['group_name'],
            'assigned_occupation_group': row['assigned_occupation_group'],

            # Technical
            'hybrid_nco_jd': row.get('hybrid_nco_jd', ''),
            'token_count': row.get('token_count', 0),
            'highest_similarity_spec': row.get('highest_similarity_spec', ''),
            'highest_similarity_score': row.get('highest_similarity_score', 0),

            # Salary
            'salary_mean_inr_month': row['salary_mean'],
            'salary_currency_unit': row['salary_currency'],
            'salary_source': row['salary_source'],

            # Computed
            'skill_count': len(row.get('skills', []))
        }

    def _ensure_category(self, row: Dict) -> Optional[str]:
        """
        Ensure category node exists and return its ID.

        Uses assigned_occupation_group primarily, falls back to group_name.
        """
        cat_name = row.get('assigned_occupation_group') or row.get('group_name')
        if not cat_name or not cat_name.strip():
            return None

        cat_name = cat_name.strip()
        cat_key = slugify(cat_name.lower())
        cat_id = f"cat:{cat_key}"

        if cat_id not in self.categories_seen:
            self.nodes[cat_id] = {
                'id': cat_id,
                'label': cat_name,
                'kind': 'category',
                'nco_code': row.get('nco_code', ''),
                'job_count': 0  # Will be updated later
            }
            self.categories_seen.add(cat_id)

        return cat_id

    def _create_skill_edges(self, job_id: str, row: Dict, normalizer: SkillNormalizer):
        """Create edges from job to skills."""
        skills = row.get('skills', [])
        if not skills:
            return

        # Sort by similarity descending for top_k filtering
        skills_sorted = sorted(
            skills,
            key=lambda s: s.get('mapping_similarity', 0),
            reverse=True
        )

        skills_added: Set[str] = set()
        edges_created = 0

        for skill_entry in skills_sorted:
            # Apply bucket filter
            if self.config.buckets:
                bucket = skill_entry.get('bucket', '')
                if bucket not in self.config.buckets:
                    self.skills_filtered_bucket += 1
                    continue

            # Apply similarity threshold
            similarity = safe_float(skill_entry.get('mapping_similarity', 0))
            if similarity < self.config.min_similarity:
                self.skills_filtered_similarity += 1
                continue

            # Get canonical skill ID
            skill_id = normalizer.get_skill_id(skill_entry.get('skill', ''))
            if not skill_id:
                continue

            # Skip duplicates within same job
            if skill_id in skills_added:
                continue

            # Create edge
            edge = {
                'source': job_id,
                'target': skill_id,
                'rel': 'REQUIRES_SKILL',
                'bucket': skill_entry.get('bucket', ''),
                'mapping_similarity': round(similarity, 4),
                'weight': round(similarity, 4)  # For Gephi
            }

            # Optionally include thinking
            if not self.config.drop_thinking:
                edge['thinking'] = skill_entry.get('thinking', '')

            self.edges.append(edge)
            skills_added.add(skill_id)
            edges_created += 1

            # Apply top_k limit
            if self.config.top_k_skills > 0 and edges_created >= self.config.top_k_skills:
                break

        if edges_created > 0:
            self.jobs_with_skills.add(job_id)
            self.skill_edges_created += edges_created

    def _add_skill_nodes(self, normalizer: SkillNormalizer):
        """Add skill nodes from the normalizer dictionary."""
        # Build set of skills with edges first (O(m) instead of O(n*m))
        logger.info("Indexing skill edges...")
        skills_with_edges = {
            e['target'] for e in self.edges
            if e['rel'] == 'REQUIRES_SKILL'
        }
        logger.info(f"Found {len(skills_with_edges):,} unique skills with edges")

        # Now iterate through dictionary and check set membership (O(1))
        for key, entry in normalizer.skill_dictionary.items():
            skill_id = f"skill:{key}"

            # Only add skills that have edges - O(1) set lookup
            if skill_id not in skills_with_edges:
                continue

            avg_sim = (
                entry['sum_similarity'] / entry['occurrence_count']
                if entry['occurrence_count'] > 0 else 0
            )

            self.nodes[skill_id] = {
                'id': skill_id,
                'label': entry['canonical_label'],
                'kind': 'skill',
                'canonical_key': key,
                'aliases': '|'.join(sorted(entry['aliases'])) if self.config.include_aliases else '',
                'job_count': entry['occurrence_count'],
                'max_similarity': round(entry['max_similarity'], 4),
                'avg_similarity': round(avg_sim, 4)
            }

    def _update_category_counts(self):
        """Update job counts for category nodes."""
        category_counts = defaultdict(int)

        for edge in self.edges:
            if edge['rel'] == 'IN_CATEGORY':
                category_counts[edge['target']] += 1

        for cat_id, count in category_counts.items():
            if cat_id in self.nodes:
                self.nodes[cat_id]['job_count'] = count

    def _count_by_kind(self, kind: str) -> int:
        """Count nodes by kind."""
        return sum(1 for n in self.nodes.values() if n.get('kind') == kind)

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        jobs = [n for n in self.nodes.values() if n['kind'] == 'job']
        skills = [n for n in self.nodes.values() if n['kind'] == 'skill']
        categories = [n for n in self.nodes.values() if n['kind'] == 'category']

        job_skill_edges = [e for e in self.edges if e['rel'] == 'REQUIRES_SKILL']
        job_cat_edges = [e for e in self.edges if e['rel'] == 'IN_CATEGORY']

        jobs_with_skills_pct = (
            len(self.jobs_with_skills) / len(jobs) * 100
            if jobs else 0
        )

        avg_skills = (
            len(job_skill_edges) / len(jobs)
            if jobs else 0
        )

        return {
            'nodes_total': len(self.nodes),
            'nodes_by_kind': {
                'job': len(jobs),
                'skill': len(skills),
                'category': len(categories)
            },
            'edges_total': len(self.edges),
            'edges_by_rel': {
                'REQUIRES_SKILL': len(job_skill_edges),
                'IN_CATEGORY': len(job_cat_edges)
            },
            'jobs_with_skills_count': len(self.jobs_with_skills),
            'jobs_with_skills_pct': round(jobs_with_skills_pct, 2),
            'jobs_with_category_count': len(self.jobs_with_category),
            'avg_skills_per_job': round(avg_skills, 2),
            'skills_filtered_by_similarity': self.skills_filtered_similarity,
            'skills_filtered_by_bucket': self.skills_filtered_bucket
        }

    def get_nodes_df(self) -> 'pd.DataFrame':
        """Get nodes as pandas DataFrame."""
        import pandas as pd
        return pd.DataFrame(list(self.nodes.values()))

    def get_edges_df(self) -> 'pd.DataFrame':
        """Get edges as pandas DataFrame."""
        import pandas as pd
        return pd.DataFrame(self.edges)
