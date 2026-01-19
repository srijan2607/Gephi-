# Sampling Strategy: Statistical and Performance Modes

## Overview

Two distinct sampling modes for different purposes:

| Mode | Purpose | Bounded By | Statistically Valid |
|------|---------|------------|---------------------|
| **stats** | Representative sample for analysis | Sample size formula | Yes |
| **perf** | Gephi-loadable subset | File size (~100MB) | No (convenience) |

---

## MODE A: Statistical Sample (`--subset_mode stats`)

### Goal
Create a sample that allows valid statistical inference about the population with specified confidence.

### Sample Size Calculation

#### For Estimating Proportions (Default)

Using Cochran's formula for sample size:

```
n₀ = (Z² × p × (1-p)) / e²

Where:
  Z = Z-score for confidence level (1.96 for 95%, 2.576 for 99%)
  p = estimated proportion (0.5 for worst-case/maximum variance)
  e = margin of error (e.g., 0.03 for ±3%)
```

With finite population correction (FPC):
```
n = n₀ / (1 + (n₀ - 1) / N)

Where:
  N = population size
  n₀ = initial sample size from Cochran's formula
```

**Example Calculation**:
```python
# Parameters
N = 60000      # Population (total jobs)
conf = 0.95    # 95% confidence
e = 0.03       # ±3% margin of error
p = 0.5        # Worst-case proportion

# Z-score lookup
Z = 1.96  # for 95% confidence

# Cochran's formula
n0 = (Z**2 * p * (1-p)) / (e**2)
n0 = (1.96**2 * 0.5 * 0.5) / (0.03**2)
n0 = (3.8416 * 0.25) / 0.0009
n0 = 1067.11

# Finite population correction
n = n0 / (1 + (n0 - 1) / N)
n = 1067.11 / (1 + 1066.11 / 60000)
n = 1067.11 / 1.0178
n = 1048.5 ≈ 1049

# Result: Need ~1049 jobs for 95% CI with ±3% margin
```

#### For Estimating Means (e.g., Salary)

```
n₀ = (Z × σ / e)²

Where:
  σ = population standard deviation (estimated from pilot)
  e = acceptable error in the mean (absolute units)
```

**Pilot Sample Process**:
```python
# 1. Draw pilot sample
pilot_n = min(1000, int(0.02 * N))  # 2% or 1000, whichever smaller
pilot_sample = random.sample(population, pilot_n)

# 2. Estimate sigma from pilot (for salary)
salaries = [row['salary_mean_inr_month'] for row in pilot_sample if row['salary_mean_inr_month']]
sigma_hat = np.std(salaries, ddof=1)

# 3. Calculate required n
e = 2000  # Acceptable error: ±2000 INR/month
n0 = (Z * sigma_hat / e)**2

# 4. Apply FPC
n = n0 / (1 + (n0 - 1) / N)
```

### Stratified Sampling

**Why Stratify?**
- Ensures all categories are represented
- Reduces variance compared to simple random sampling
- Preserves population structure

**Proportional Allocation**:
```python
# For each stratum h (category):
n_h = n × (N_h / N)

Where:
  n_h = sample size for stratum h
  N_h = population size of stratum h
  N = total population
  n = total sample size
```

**Minimum Per Stratum**:
```python
min_per_stratum = 30  # Default (for CLT assumptions)

# Adjusted allocation:
for stratum in strata:
    n_h = max(min_per_stratum, proportional_allocation(stratum))

# If sum(n_h) > n, we have a problem:
#   Option 1: Increase total n
#   Option 2: Reduce min_per_stratum
#   Option 3: Collapse small categories into "Other"
```

### Graph Integrity Preservation

**Critical Rule**: For every sampled job, include ALL its connected nodes.

```python
def sample_with_graph_integrity(sampled_job_ids, full_graph):
    nodes_to_include = set()
    edges_to_include = set()

    for job_id in sampled_job_ids:
        # Include job node
        nodes_to_include.add(job_id)

        # Include category node
        category_id = get_category(job_id)
        nodes_to_include.add(category_id)
        edges_to_include.add((job_id, category_id))

        # Include ALL skill nodes for this job
        for skill_id, edge_attrs in get_job_skills(job_id):
            nodes_to_include.add(skill_id)
            edges_to_include.add((job_id, skill_id, edge_attrs))

    return nodes_to_include, edges_to_include
```

### Output: stats_subset_report.json

```json
{
  "sampling_mode": "stats",
  "population": {
    "total_jobs": 60000,
    "total_categories": 123
  },
  "parameters": {
    "confidence_level": 0.95,
    "margin_of_error": 0.03,
    "p_estimate": 0.5,
    "finite_correction": true,
    "min_per_category": 30
  },
  "formulas": {
    "cochran_n0": "Z² × p × (1-p) / e² = 1067.11",
    "fpc_n": "n0 / (1 + (n0-1)/N) = 1049"
  },
  "sample": {
    "target_n": 1049,
    "actual_n": 1052,
    "actual_confidence": 0.9503
  },
  "stratification": {
    "Software Developers": {"population": 12000, "sample": 210},
    "Data Analysts": {"population": 8000, "sample": 140},
    ...
  },
  "graph_stats": {
    "nodes_total": 15234,
    "nodes_jobs": 1052,
    "nodes_skills": 14059,
    "nodes_categories": 123,
    "edges_total": 18456
  },
  "warnings": [
    "Category 'Rare Occupation' has only 15 jobs; sampled all 15 (below min_per_category=30)"
  ]
}
```

---

## MODE B: Performance Sample (`--subset_mode perf`)

### Goal
Create a Gephi-loadable subset bounded by file size, not statistical validity.

### Algorithm

```python
def performance_sample(data, config):
    max_bytes = config.get('max_bytes', 100_000_000)  # 100MB default
    seed = config.get('seed', 42)
    top_k_skills = config.get('top_k_skills_per_job', 10)
    min_similarity = config.get('min_similarity', 0.55)
    drop_thinking = config.get('drop_thinking', True)

    random.seed(seed)

    # Step 1: Select categories
    if config.get('category_list'):
        categories = config['category_list']
    else:
        # Top K categories by job count
        categories = get_top_categories(config.get('num_categories', 30))

    # Step 2: Get jobs in selected categories
    eligible_jobs = [j for j in data if j['category'] in categories]

    # Step 3: Estimate bytes per job
    avg_bytes_per_job = estimate_job_size(
        include_thinking=not drop_thinking,
        avg_skills=top_k_skills
    )

    # Step 4: Calculate max jobs
    max_jobs = int(max_bytes / avg_bytes_per_job * 0.8)  # 80% safety margin

    # Step 5: Stratified sample within budget
    sampled_jobs = stratified_sample(eligible_jobs, max_jobs, by='category')

    # Step 6: Apply edge filters
    for job in sampled_jobs:
        job['skills'] = filter_skills(
            job['skills'],
            top_k=top_k_skills,
            min_similarity=min_similarity
        )

    # Step 7: Build graph with filtered data
    return build_graph(sampled_jobs, drop_thinking=drop_thinking)
```

### Size Estimation

```python
def estimate_job_size(include_thinking=False, avg_skills=10):
    """Estimate bytes per job in output."""
    # Node size (job)
    job_node_size = 500  # ~500 bytes for job node with all attributes

    # Edge sizes
    category_edge_size = 100  # Job→Category edge
    skill_edge_size = 150 if not include_thinking else 500  # Job→Skill edge

    # Skill nodes (shared, so amortized)
    skill_node_amortized = 50  # Each skill shared across many jobs

    total = job_node_size + category_edge_size
    total += avg_skills * (skill_edge_size + skill_node_amortized)

    return total  # ~2000-3000 bytes per job typically
```

### Edge Filtering Options

```python
def filter_skills(skills, top_k=10, min_similarity=0.55):
    """Filter skills for lightweight export."""
    # Remove below threshold
    filtered = [s for s in skills if s['mapping_similarity'] >= min_similarity]

    # Sort by similarity descending
    filtered.sort(key=lambda s: s['mapping_similarity'], reverse=True)

    # Take top K
    return filtered[:top_k]
```

### Output: perf_subset_report.json

```json
{
  "sampling_mode": "perf",
  "constraints": {
    "max_bytes": 100000000,
    "top_k_skills_per_job": 10,
    "min_similarity": 0.55,
    "drop_thinking": true,
    "num_categories": 30
  },
  "result": {
    "jobs_sampled": 8500,
    "categories_included": 30,
    "skills_unique": 4200,
    "edges_total": 95000,
    "estimated_size_bytes": 95000000,
    "actual_size_bytes": 94523456
  },
  "seed": 42
}
```

---

## CLI Specification

```bash
# Statistical sample (Goal A)
python build_graph.py \
  --input data.csv \
  --outdir ./output \
  --subset true \
  --subset_mode stats \
  --conf_level 0.95 \
  --margin_error 0.03 \
  --min_per_category 30 \
  --finite_correction true

# Performance sample (Goal B)
python build_graph.py \
  --input data.csv \
  --outdir ./output \
  --subset true \
  --subset_mode perf \
  --subset_max_bytes 100000000 \
  --subset_seed 42 \
  --top_k_skills 10 \
  --min_similarity 0.55 \
  --drop_thinking true

# Full graph (no sampling)
python build_graph.py \
  --input data.csv \
  --outdir ./output \
  --subset false
```

---

## Comparison: stats vs perf

| Aspect | stats mode | perf mode |
|--------|------------|-----------|
| Sample size determined by | Statistical formula | File size limit |
| Statistically valid | Yes | No |
| Reproducible | Yes (deterministic) | Yes (with seed) |
| Graph complete | Yes (all edges) | No (filtered edges) |
| Good for | Analysis, publication | Gephi exploration |
| Typical output size | Varies (formula-based) | ~100MB (configured) |
