# Validation and Testing Strategy

## Validation Metrics

### 1. Skill Deduplication Effectiveness

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Unique skills before | ~233,000 | Count distinct skill strings in input |
| Unique skills after | <25,000 | Count skill nodes in graph |
| Dedup ratio | >90% | `1 - (after/before)` |
| Top skill overlap | >1000 jobs | Top 10 skills should each appear in 1000+ jobs |

**Validation Code**:
```python
def validate_skill_dedup(input_skills, graph):
    raw_count = len(set(input_skills))
    canonical_count = len([n for n in graph.nodes.values() if n['kind'] == 'skill'])

    dedup_ratio = 1 - (canonical_count / raw_count)
    assert dedup_ratio > 0.90, f"Dedup ratio {dedup_ratio:.2%} below target"

    # Check top skills have overlap
    skill_counts = Counter()
    for edge in graph.edges:
        if edge['rel'] == 'REQUIRES_SKILL':
            skill_counts[edge['target']] += 1

    top_10 = skill_counts.most_common(10)
    for skill_id, count in top_10:
        assert count > 1000, f"Top skill {skill_id} only in {count} jobs"
```

### 2. Job Metadata Completeness

| Field | Target Coverage | Validation |
|-------|-----------------|------------|
| job_title | 100% | Required |
| company_name | >95% | Warn if missing |
| district | >90% | Warn if missing |
| nco_code | >95% | Warn if missing |
| salary_mean | >30% | Log sparsity |
| schedule_type | >80% | Warn if missing |

**Validation Code**:
```python
def validate_job_metadata(graph):
    jobs = [n for n in graph.nodes.values() if n['kind'] == 'job']

    coverage = {}
    fields = ['job_title', 'company_name', 'district', 'nco_code',
              'salary_mean_inr_month', 'schedule_type']

    for field in fields:
        non_empty = sum(1 for j in jobs if j.get(field))
        coverage[field] = non_empty / len(jobs) * 100

    assert coverage['job_title'] == 100, "Missing job titles"
    if coverage['company_name'] < 95:
        logging.warning(f"Company name coverage: {coverage['company_name']:.1f}%")

    return coverage
```

### 3. Edge Integrity

| Metric | Target | Description |
|--------|--------|-------------|
| Jobs with skill edges | >98% | Nearly all jobs should have skills |
| Jobs with category edges | 100% | All jobs must have a category |
| Orphan skills | 0 | All skills must be connected to jobs |
| Avg skills per job | 8-15 | Reasonable range |

**Validation Code**:
```python
def validate_edges(graph):
    jobs = {n['id'] for n in graph.nodes.values() if n['kind'] == 'job'}
    skills = {n['id'] for n in graph.nodes.values() if n['kind'] == 'skill'}

    # Jobs with skill edges
    jobs_with_skills = set()
    skill_edge_count = 0
    connected_skills = set()

    for edge in graph.edges:
        if edge['rel'] == 'REQUIRES_SKILL':
            jobs_with_skills.add(edge['source'])
            connected_skills.add(edge['target'])
            skill_edge_count += 1

    pct_with_skills = len(jobs_with_skills) / len(jobs) * 100
    assert pct_with_skills > 98, f"Only {pct_with_skills:.1f}% jobs have skills"

    # Orphan skills
    orphan_skills = skills - connected_skills
    assert len(orphan_skills) == 0, f"{len(orphan_skills)} orphan skills found"

    # Average skills per job
    avg_skills = skill_edge_count / len(jobs)
    assert 5 < avg_skills < 20, f"Avg skills/job {avg_skills:.1f} outside expected range"
```

### 4. GraphML Validity

| Check | Method |
|-------|--------|
| Well-formed XML | Parse with lxml |
| No empty IDs | Regex check |
| All edges reference existing nodes | Set membership |
| Proper escaping | Check for unescaped &, <, > |

**Validation Code**:
```python
def validate_graphml(filepath):
    from lxml import etree

    # Parse XML
    try:
        tree = etree.parse(filepath)
    except etree.XMLSyntaxError as e:
        raise AssertionError(f"Invalid XML: {e}")

    root = tree.getroot()
    ns = {'g': 'http://graphml.graphdrawing.org/xmlns'}

    # Check no empty IDs
    nodes = root.findall('.//g:node', ns)
    for node in nodes:
        node_id = node.get('id')
        assert node_id and node_id.strip(), "Empty node ID found"

    edges = root.findall('.//g:edge', ns)
    node_ids = {n.get('id') for n in nodes}

    for edge in edges:
        source = edge.get('source')
        target = edge.get('target')
        assert source in node_ids, f"Edge source {source} not in nodes"
        assert target in node_ids, f"Edge target {target} not in nodes"
```

### 5. Sampling Validity

#### Statistical Sample Checks
```python
def validate_stats_sample(sample, population, config):
    # Sample size meets formula
    expected_n = calculate_sample_size(len(population), config)
    assert len(sample) >= expected_n * 0.95, "Sample too small"

    # All categories represented
    pop_categories = set(j['category'] for j in population)
    sample_categories = set(j['category'] for j in sample)
    assert sample_categories == pop_categories, "Missing categories in sample"

    # Minimum per category
    category_counts = Counter(j['category'] for j in sample)
    for cat, count in category_counts.items():
        if pop_category_size[cat] >= config.min_per_category:
            assert count >= config.min_per_category, f"Category {cat} undersampled"
```

#### Performance Sample Checks
```python
def validate_perf_sample(output_path, config):
    # File size within bounds
    size = os.path.getsize(output_path)
    assert size <= config.max_bytes * 1.1, f"File {size} exceeds limit"

    # Reproducibility
    # Run twice with same seed, compare outputs
```

---

## Test Cases

### Unit Tests: Skill Normalization

```python
class TestSkillNormalization(unittest.TestCase):

    def test_lowercase(self):
        assert normalize_skill("PYTHON") == "python"
        assert normalize_skill("Python") == "python"

    def test_whitespace(self):
        assert normalize_skill("  Python  ") == "python"
        assert normalize_skill("machine   learning") == "machine learning"

    def test_punctuation(self):
        assert normalize_skill("Python.") == "python"
        assert normalize_skill("Excel,") == "excel"

    def test_dashes(self):
        assert normalize_skill("front-end") == "front-end"
        assert normalize_skill("front–end") == "front-end"  # en-dash
        assert normalize_skill("front / end") == "front-end"

    def test_abbreviations(self):
        assert normalize_skill("R&D") == "r and d"
        assert normalize_skill("w/ clients") == "with clients"

    def test_merge_variants(self):
        # These should all produce the same canonical key
        variants = ["Python", "python", "PYTHON", "  python  ", "Python."]
        keys = [skill_key(v) for v in variants]
        assert len(set(keys)) == 1, "Variants not merging"
```

### Unit Tests: JSON Parsing

```python
class TestSkillsParsing(unittest.TestCase):

    def test_valid_json(self):
        json_str = '[{"skill":"Python","bucket":"Advanced","mapping_similarity":0.9}]'
        result = parse_skills_json(json_str)
        assert len(result) == 1
        assert result[0]['skill'] == 'Python'

    def test_empty_string(self):
        assert parse_skills_json("") == []
        assert parse_skills_json(None) == []

    def test_malformed_json(self):
        with pytest.raises(ValueError):
            parse_skills_json("[{invalid json")

    def test_not_array(self):
        assert parse_skills_json('{"skill":"Python"}') == []
```

### Integration Tests

```python
class TestEndToEnd(unittest.TestCase):

    def test_small_dataset(self):
        """Process test fixture, verify outputs."""
        result = subprocess.run([
            'python', 'build_graph.py',
            '--input', 'tests/fixtures/small.csv',
            '--outdir', 'tests/output'
        ])
        assert result.returncode == 0

        # Check files exist
        assert os.path.exists('tests/output/nodes.csv')
        assert os.path.exists('tests/output/edges.csv')
        assert os.path.exists('tests/output/graph.graphml')
        assert os.path.exists('tests/output/report.json')

        # Load and verify report
        with open('tests/output/report.json') as f:
            report = json.load(f)

        assert report['quality']['jobs_with_skills_pct'] > 95
```

---

## report.json Schema

```json
{
  "meta": {
    "version": "2.0.0",
    "timestamp": "2025-01-19T12:00:00Z",
    "input_file": "/path/to/data.csv",
    "output_dir": "/path/to/output"
  },
  "config": {
    "formats": ["csv", "graphml"],
    "drop_thinking": true,
    "min_similarity": 0.0,
    "top_k_skills": 0,
    "subset": false
  },
  "input": {
    "rows_total": 60000,
    "rows_parsed": 59850,
    "rows_failed": 150,
    "columns": ["Job Title", "Company Name", "..."]
  },
  "normalization": {
    "raw_skill_strings": 233000,
    "canonical_skills": 12500,
    "dedup_ratio": 0.946,
    "top_skills": [
      {"skill": "communication", "count": 45000},
      {"skill": "microsoft-excel", "count": 38000}
    ]
  },
  "graph": {
    "nodes_total": 72350,
    "nodes_by_kind": {
      "job": 59850,
      "skill": 12377,
      "category": 123
    },
    "edges_total": 520000,
    "edges_by_rel": {
      "REQUIRES_SKILL": 460150,
      "IN_CATEGORY": 59850
    }
  },
  "quality": {
    "jobs_with_skills_pct": 98.5,
    "jobs_with_category_pct": 100.0,
    "avg_skills_per_job": 7.69,
    "orphan_skills": 0,
    "metadata_coverage": {
      "job_title": 100.0,
      "company_name": 96.2,
      "district": 91.5,
      "salary_mean": 32.1
    }
  },
  "output_files": {
    "nodes.csv": {"path": "...", "size_bytes": 45000000, "rows": 72350},
    "edges.csv": {"path": "...", "size_bytes": 120000000, "rows": 520000},
    "graph.graphml": {"path": "...", "size_bytes": 180000000}
  },
  "sampling": null,
  "warnings": [
    "150 rows failed to parse (see bad_rows.csv)",
    "Salary data present in only 32.1% of jobs"
  ],
  "errors": []
}
```

---

## Gephi Import Verification

After running the builder, manually verify in Gephi:

1. **Open graph.graphml** → Should load without errors
2. **Data Laboratory** → Verify all columns present:
   - Nodes: id, label, kind, company_name, district, salary, etc.
   - Edges: source, target, rel, bucket, mapping_similarity, weight
3. **Partition by 'kind'** → Should see 3 colors (job/skill/category)
4. **Filter by salary** → Should be able to filter jobs by salary range
5. **Run modularity** → Should detect meaningful communities
6. **Size by degree** → Skills should vary in size based on popularity
