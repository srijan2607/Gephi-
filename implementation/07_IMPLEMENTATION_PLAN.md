# Implementation Plan

## Project Structure

```
job-graph-converter/
├── build_graph.py              # CLI entry point
├── graph_builder/              # Python package
│   ├── __init__.py
│   ├── config.py               # Configuration and CLI parsing
│   ├── parser.py               # CSV/Excel parsing with streaming
│   ├── normalizer.py           # Skill canonicalization
│   ├── graph.py                # Graph construction
│   ├── sampler.py              # Statistical and performance sampling
│   ├── exporter.py             # CSV, GraphML export
│   ├── validator.py            # Quality checks and reporting
│   └── utils.py                # Utilities (slugify, logging, etc.)
├── implementation/             # Planning documents (this folder)
├── tests/                      # Unit tests
│   ├── test_normalizer.py
│   ├── test_sampler.py
│   └── test_fixtures/
├── output/                     # Default output directory
└── README.md                   # Documentation
```

## Implementation Phases

### Phase 1: Core Infrastructure
**Files**: `config.py`, `utils.py`, `build_graph.py`

#### 1.1 Configuration Module (`config.py`)
```python
# Responsibilities:
# - Parse CLI arguments using argparse
# - Validate argument combinations
# - Provide default values
# - Export configuration as dict

class Config:
    def __init__(self, args):
        self.input_path = args.input
        self.output_dir = args.outdir
        self.formats = args.format.split(',')
        # ... all other options

    def validate(self):
        # Check file exists
        # Check output dir writable
        # Validate argument combinations

    def to_dict(self):
        # For report.json
```

#### 1.2 Utilities Module (`utils.py`)
```python
# Functions:
def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""

def escape_xml(text: str) -> str:
    """Escape special characters for XML."""

def setup_logging(verbose: bool) -> logging.Logger:
    """Configure logging."""

def safe_float(val, default=0.0) -> float:
    """Parse float safely."""

def safe_json_loads(text: str) -> Optional[list]:
    """Parse JSON with error handling."""
```

#### 1.3 CLI Entry Point (`build_graph.py`)
```python
#!/usr/bin/env python3
"""
Job-Skills Graph Builder

Usage:
    python build_graph.py --input data.csv --outdir ./output
"""

def main():
    config = Config.from_args()
    config.validate()

    # Phase 1: Parse input
    parser = DataParser(config)
    raw_data = parser.parse()

    # Phase 2: Normalize skills
    normalizer = SkillNormalizer()
    normalized_data, skill_dict = normalizer.process(raw_data)

    # Phase 3: Build graph
    builder = GraphBuilder(config)
    graph = builder.build(normalized_data, skill_dict)

    # Phase 4: Sample (if requested)
    if config.subset:
        sampler = get_sampler(config.subset_mode)
        graph = sampler.sample(graph, config)

    # Phase 5: Export
    exporter = Exporter(config)
    exporter.export(graph, skill_dict)

    # Phase 6: Validate and report
    validator = Validator(config)
    report = validator.validate(graph)
    validator.write_report(report)

if __name__ == '__main__':
    main()
```

---

### Phase 2: Data Parsing
**File**: `parser.py`

#### 2.1 Streaming CSV/Excel Reader
```python
class DataParser:
    def __init__(self, config):
        self.config = config
        self.bad_rows = []

    def parse(self) -> Generator[dict, None, None]:
        """Yield parsed rows one at a time."""
        if self.config.input_path.endswith('.csv'):
            yield from self._parse_csv()
        else:
            yield from self._parse_excel()

    def _parse_csv(self):
        for chunk in pd.read_csv(
            self.config.input_path,
            chunksize=self.config.chunk_size,
            dtype=str,  # Read all as string initially
            na_values=['', 'NA', 'N/A', 'null', 'NULL']
        ):
            for _, row in chunk.iterrows():
                parsed = self._parse_row(row)
                if parsed:
                    yield parsed

    def _parse_row(self, row: pd.Series) -> Optional[dict]:
        """Parse a single row, handling errors."""
        try:
            # Parse skills JSON
            skills_raw = row.get(self.config.skills_column, '')
            skills = self._parse_skills_json(skills_raw)

            return {
                'job_id': self._get_job_id(row),
                'job_title': str(row.get('Job Title', '')).strip(),
                'company_name': str(row.get('Company Name', '')).strip(),
                'posted_at': str(row.get('Posted At', '')).strip(),
                'schedule_type': str(row.get('Schedule Type', '')).strip(),
                'work_from_home': self._parse_wfh(row.get('Work From Home', '')),
                'district': str(row.get('District', '')).strip(),
                'nco_code': str(row.get('NCO Code', '')).strip(),
                'group_name': str(row.get('Group', '')).strip(),
                'assigned_occupation_group': str(row.get('Assigned_Occupation_Group', '')).strip(),
                'salary_mean': safe_float(row.get('salary_mean_inr_month')),
                'salary_currency': str(row.get('salary_currency_unit', '')).strip(),
                'salary_source': str(row.get('salary_source', '')).strip(),
                'token_count': safe_int(row.get('token_count', 0)),
                'highest_similarity_spec': str(row.get('Highest Similarity Spec', '')).strip(),
                'highest_similarity_score': safe_float(row.get('Highest Similarity Score Spec', 0)),
                'skills': skills,
                '_row_num': row.name  # For error tracking
            }
        except Exception as e:
            self.bad_rows.append({
                'row_num': row.name,
                'job_id': row.get('Job Title', 'unknown'),
                'error': str(e)
            })
            return None

    def _parse_skills_json(self, text: str) -> list:
        """Parse skills JSON array."""
        if not text or pd.isna(text):
            return []

        try:
            skills = json.loads(text)
            if not isinstance(skills, list):
                return []
            return skills
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid skills JSON: {e}")
```

---

### Phase 3: Skill Canonicalization
**File**: `normalizer.py`

#### 3.1 Skill Normalizer
```python
class SkillNormalizer:
    def __init__(self):
        self.skill_dictionary = {}  # canonical_key -> SkillEntry
        self.alias_map = {}         # original -> canonical_key

    def process(self, data_generator):
        """Two-pass processing: build dictionary, then normalize."""
        # Pass 1: Build skill dictionary
        rows = []
        for row in data_generator:
            rows.append(row)
            for skill_entry in row.get('skills', []):
                self._register_skill(skill_entry)

        # Pass 2: Normalize skills in each row
        for row in rows:
            row['skills'] = self._normalize_row_skills(row['skills'])
            yield row

    def _register_skill(self, skill_entry: dict):
        """Register a skill in the dictionary."""
        raw_label = skill_entry.get('skill', '')
        if not raw_label or not raw_label.strip():
            return

        canonical_key = self._canonicalize(raw_label)
        if not canonical_key:
            return

        if canonical_key not in self.skill_dictionary:
            self.skill_dictionary[canonical_key] = {
                'canonical_key': canonical_key,
                'canonical_label': self._title_case(raw_label),
                'aliases': set(),
                'occurrence_count': 0,
                'max_similarity': 0.0,
                'buckets': set()
            }

        entry = self.skill_dictionary[canonical_key]
        entry['aliases'].add(raw_label.strip())
        entry['occurrence_count'] += 1
        entry['max_similarity'] = max(
            entry['max_similarity'],
            skill_entry.get('mapping_similarity', 0)
        )
        entry['buckets'].add(skill_entry.get('bucket', ''))
        self.alias_map[raw_label.strip()] = canonical_key

    def _canonicalize(self, raw_label: str) -> str:
        """Convert raw skill label to canonical key."""
        s = raw_label.strip().lower()

        # Remove trailing punctuation
        s = re.sub(r'[.,:;!?]+$', '', s)

        # Normalize whitespace
        s = re.sub(r'\s+', ' ', s)

        # Normalize dashes
        s = s.replace('–', '-').replace('—', '-')
        s = re.sub(r'\s*[-/]\s*', '-', s)

        # Expand abbreviations
        s = re.sub(r'\b&\b', ' and ', s)
        s = re.sub(r'\bw/\b', 'with ', s)

        # Generate slug
        return slugify(s.strip())

    def get_skill_id(self, raw_label: str) -> str:
        """Get the skill node ID for a raw label."""
        canonical_key = self.alias_map.get(raw_label.strip())
        if canonical_key:
            return f"skill:{canonical_key}"
        return None

    def export_dictionary(self) -> pd.DataFrame:
        """Export skill dictionary as DataFrame."""
        records = []
        for key, entry in self.skill_dictionary.items():
            records.append({
                'skill_id': f"skill:{key}",
                'canonical_key': key,
                'canonical_label': entry['canonical_label'],
                'aliases': '|'.join(sorted(entry['aliases'])),
                'occurrence_count': entry['occurrence_count'],
                'max_similarity': entry['max_similarity']
            })
        return pd.DataFrame(records)
```

---

### Phase 4: Graph Construction
**File**: `graph.py`

#### 4.1 Graph Builder
```python
class GraphBuilder:
    def __init__(self, config):
        self.config = config
        self.nodes = {}  # id -> node dict
        self.edges = []  # list of edge dicts

    def build(self, data_generator, skill_normalizer):
        """Build the graph from normalized data."""
        categories_seen = set()

        for row in data_generator:
            # Create job node
            job_id = f"job:{row['job_id']}"
            self.nodes[job_id] = self._create_job_node(row)

            # Create/reference category node
            category_id = self._ensure_category(row, categories_seen)
            if category_id:
                self.edges.append({
                    'source': job_id,
                    'target': category_id,
                    'rel': 'IN_CATEGORY'
                })

            # Create skill edges
            skills_added = set()
            for skill_entry in row.get('skills', []):
                skill_id = skill_normalizer.get_skill_id(skill_entry.get('skill', ''))
                if not skill_id or skill_id in skills_added:
                    continue

                # Apply filters
                similarity = skill_entry.get('mapping_similarity', 0)
                if similarity < self.config.min_similarity:
                    continue

                self.edges.append({
                    'source': job_id,
                    'target': skill_id,
                    'rel': 'REQUIRES_SKILL',
                    'bucket': skill_entry.get('bucket', ''),
                    'mapping_similarity': similarity,
                    'thinking': skill_entry.get('thinking', '') if not self.config.drop_thinking else None,
                    'weight': similarity  # For Gephi
                })
                skills_added.add(skill_id)

                # Apply top_k filter
                if self.config.top_k_skills > 0 and len(skills_added) >= self.config.top_k_skills:
                    break

        # Add skill nodes from dictionary
        for key, entry in skill_normalizer.skill_dictionary.items():
            skill_id = f"skill:{key}"
            self.nodes[skill_id] = {
                'id': skill_id,
                'label': entry['canonical_label'],
                'kind': 'skill',
                'canonical_key': key,
                'aliases': '|'.join(sorted(entry['aliases'])),
                'job_count': entry['occurrence_count'],
                'avg_similarity': entry['max_similarity']
            }

        return self

    def _create_job_node(self, row):
        return {
            'id': f"job:{row['job_id']}",
            'label': row['job_title'],
            'kind': 'job',
            'job_title': row['job_title'],
            'company_name': row['company_name'],
            'posted_at': row['posted_at'],
            'schedule_type': row['schedule_type'],
            'work_from_home': row['work_from_home'],
            'district': row['district'],
            'nco_code': row['nco_code'],
            'group_name': row['group_name'],
            'salary_mean_inr_month': row['salary_mean'],
            'salary_source': row['salary_source'],
            'skill_count': len(row.get('skills', []))
        }

    def _ensure_category(self, row, categories_seen):
        cat_name = row.get('assigned_occupation_group') or row.get('group_name')
        if not cat_name:
            return None

        cat_id = f"cat:{slugify(cat_name.lower())}"
        if cat_id not in categories_seen:
            self.nodes[cat_id] = {
                'id': cat_id,
                'label': cat_name,
                'kind': 'category',
                'nco_code': row.get('nco_code', '')
            }
            categories_seen.add(cat_id)
        return cat_id
```

---

### Phase 5: Sampling
**File**: `sampler.py`

#### 5.1 Base Sampler
```python
class BaseSampler:
    def sample(self, graph, config):
        raise NotImplementedError

class StatisticalSampler(BaseSampler):
    """Implements Cochran's formula with stratification."""

    def sample(self, graph, config):
        # Calculate sample size
        N = len([n for n in graph.nodes.values() if n['kind'] == 'job'])
        n = self._calculate_sample_size(N, config)

        # Stratify by category
        strata = self._stratify_jobs(graph, config)

        # Allocate samples per stratum
        allocation = self._allocate_proportional(strata, n, config)

        # Sample from each stratum
        sampled_job_ids = self._sample_strata(strata, allocation, config)

        # Build subgraph with graph integrity
        return self._build_subgraph(graph, sampled_job_ids)

    def _calculate_sample_size(self, N, config):
        """Cochran's formula with FPC."""
        Z = self._z_score(config.conf_level)
        p = 0.5 if config.p_worstcase else config.p_estimate
        e = config.margin_error

        n0 = (Z**2 * p * (1-p)) / (e**2)

        if config.finite_correction:
            n = n0 / (1 + (n0 - 1) / N)
        else:
            n = n0

        return int(np.ceil(n))

class PerformanceSampler(BaseSampler):
    """Size-bounded sampling for Gephi."""

    def sample(self, graph, config):
        # Estimate max jobs for target size
        max_jobs = self._estimate_max_jobs(config)

        # Select categories
        categories = self._select_categories(graph, config)

        # Sample jobs within categories
        sampled_job_ids = self._sample_within_budget(graph, categories, max_jobs, config)

        # Build subgraph
        return self._build_subgraph(graph, sampled_job_ids)
```

---

### Phase 6: Export
**File**: `exporter.py`

#### 6.1 Multi-format Exporter
```python
class Exporter:
    def __init__(self, config):
        self.config = config

    def export(self, graph, skill_normalizer):
        os.makedirs(self.config.output_dir, exist_ok=True)

        if 'csv' in self.config.formats:
            self._export_csv(graph)

        if 'graphml' in self.config.formats:
            self._export_graphml(graph)

        # Always export these
        self._export_skill_dictionary(skill_normalizer)
        self._export_bad_rows()

    def _export_graphml(self, graph):
        """Stream GraphML to file."""
        path = os.path.join(self.config.output_dir, 'graph.graphml')

        with open(path, 'w', encoding='utf-8') as f:
            # Write header
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write('<graphml xmlns="http://graphml.graphdrawing.org/xmlns">\n')

            # Write key definitions
            self._write_graphml_keys(f)

            f.write('  <graph id="G" edgedefault="directed">\n')

            # Write nodes
            for node_id, node in graph.nodes.items():
                f.write(self._node_to_graphml(node))

            # Write edges
            for edge in graph.edges:
                f.write(self._edge_to_graphml(edge))

            f.write('  </graph>\n')
            f.write('</graphml>\n')
```

---

### Phase 7: Validation
**File**: `validator.py`

```python
class Validator:
    def validate(self, graph, parser):
        report = {
            'input': {...},
            'graph': {...},
            'quality': {...},
            'warnings': []
        }

        # Count by type
        jobs = [n for n in graph.nodes.values() if n['kind'] == 'job']
        skills = [n for n in graph.nodes.values() if n['kind'] == 'skill']
        categories = [n for n in graph.nodes.values() if n['kind'] == 'category']

        report['graph'] = {
            'total_nodes': len(graph.nodes),
            'jobs': len(jobs),
            'skills': len(skills),
            'categories': len(categories),
            'edges_total': len(graph.edges),
            'edges_job_skill': len([e for e in graph.edges if e['rel'] == 'REQUIRES_SKILL']),
            'edges_job_category': len([e for e in graph.edges if e['rel'] == 'IN_CATEGORY'])
        }

        # Quality checks
        jobs_with_skills = len([j for j in jobs if self._has_skill_edge(j['id'], graph)])
        report['quality'] = {
            'jobs_with_skills_pct': jobs_with_skills / len(jobs) * 100,
            'avg_skills_per_job': report['graph']['edges_job_skill'] / len(jobs),
            'skill_dedup_ratio': original_skills / len(skills),
            'bad_rows_count': len(parser.bad_rows)
        }

        # Assertions
        if report['quality']['jobs_with_skills_pct'] < 95:
            report['warnings'].append(
                f"Only {report['quality']['jobs_with_skills_pct']:.1f}% of jobs have skill edges"
            )

        return report
```

---

## Implementation Order

1. **Day 1**: `utils.py`, `config.py`, basic CLI scaffold
2. **Day 2**: `parser.py` with streaming and error handling
3. **Day 3**: `normalizer.py` with canonicalization
4. **Day 4**: `graph.py` with full schema
5. **Day 5**: `exporter.py` for CSV and GraphML
6. **Day 6**: `sampler.py` for both modes
7. **Day 7**: `validator.py` and integration testing
8. **Day 8**: Documentation and edge cases
