# CLI Specification

## Command Structure

```bash
python build_graph.py [OPTIONS]
```

## Required Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `--input` | PATH | Input CSV or Excel file |
| `--outdir` | PATH | Output directory (created if not exists) |

## Output Format Options

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--format` | STRING | `csv,graphml` | Output formats (comma-separated) |
| `--drop_thinking` | BOOL | `true` | Omit "thinking" field from edges |
| `--include_aliases` | BOOL | `true` | Include skill aliases in output |

## Edge Filtering Options

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--min_similarity` | FLOAT | `0.0` | Minimum mapping_similarity threshold |
| `--top_k_skills` | INT | `0` | Max skills per job (0 = all) |
| `--buckets` | STRING | `all` | Filter by bucket (comma-separated or "all") |

## Sampling Options

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--subset` | BOOL | `false` | Enable subset sampling |
| `--subset_mode` | STRING | `perf` | Sampling mode: `stats` or `perf` |

### Statistical Sampling (`--subset_mode stats`)

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--conf_level` | FLOAT | `0.95` | Confidence level (0.90, 0.95, 0.99) |
| `--margin_error` | FLOAT | `0.03` | Margin of error for proportions |
| `--p_worstcase` | BOOL | `true` | Use p=0.5 for worst-case variance |
| `--p_estimate` | FLOAT | `0.5` | Estimated proportion (if not worst-case) |
| `--finite_correction` | BOOL | `true` | Apply finite population correction |
| `--min_per_category` | INT | `30` | Minimum samples per category |
| `--mean_target_column` | STRING | `null` | Column for mean estimation |
| `--mean_margin_error` | FLOAT | `2000` | Absolute error for mean |

### Performance Sampling (`--subset_mode perf`)

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--subset_max_bytes` | INT | `100000000` | Target file size (bytes) |
| `--subset_seed` | INT | `42` | Random seed for reproducibility |
| `--subset_categories` | INT | `0` | Limit to top N categories (0 = all) |
| `--category_list` | STRING | `null` | Specific categories (comma-separated) |

## Processing Options

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--chunk_size` | INT | `10000` | Rows per chunk for streaming |
| `--skills_column` | STRING | `importance_standardised` | Column with skills JSON |
| `--category_column` | STRING | `Assigned_Occupation_Group` | Column for categories |
| `--job_id_column` | STRING | `auto` | Column for job ID (auto-detect) |
| `--verbose` | BOOL | `false` | Enable verbose logging |

## Example Commands

### Full Graph Export (All Data)

```bash
# CSV + GraphML, all skills, all metadata
python build_graph.py \
  --input /path/to/jobs.csv \
  --outdir ./output \
  --format csv,graphml \
  --drop_thinking true
```

### Lightweight Gephi Export

```bash
# Filtered for Gephi performance
python build_graph.py \
  --input /path/to/jobs.csv \
  --outdir ./output \
  --format graphml \
  --drop_thinking true \
  --min_similarity 0.6 \
  --top_k_skills 10
```

### Statistical Sample for Research

```bash
# Representative sample with 95% CI, ±3% margin
python build_graph.py \
  --input /path/to/jobs.csv \
  --outdir ./output_stats \
  --subset true \
  --subset_mode stats \
  --conf_level 0.95 \
  --margin_error 0.03 \
  --min_per_category 30
```

### Performance Sample for Gephi

```bash
# ~100MB file for Gephi exploration
python build_graph.py \
  --input /path/to/jobs.csv \
  --outdir ./output_perf \
  --subset true \
  --subset_mode perf \
  --subset_max_bytes 100000000 \
  --subset_seed 42 \
  --top_k_skills 10 \
  --min_similarity 0.55
```

### Salary Analysis Sample

```bash
# Sample sized for salary mean estimation
python build_graph.py \
  --input /path/to/jobs.csv \
  --outdir ./output_salary \
  --subset true \
  --subset_mode stats \
  --mean_target_column salary_mean_inr_month \
  --mean_margin_error 1500 \
  --conf_level 0.95
```

## Output Files

For each run, the following files are produced:

| File | Description |
|------|-------------|
| `nodes.csv` | All nodes with attributes |
| `edges.csv` | All edges with attributes |
| `graph.graphml` | GraphML for Gephi (if requested) |
| `skill_dictionary.csv` | Skill normalization mapping |
| `bad_rows.csv` | Failed rows with error reasons |
| `report.json` | Metrics, validation, and parameters |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Invalid arguments |
| 2 | Input file not found |
| 3 | Parse errors exceeded threshold |
| 4 | Output write failure |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GRAPH_BUILDER_LOG_LEVEL` | Logging level (DEBUG, INFO, WARN, ERROR) |
| `GRAPH_BUILDER_CHUNK_SIZE` | Default chunk size override |
