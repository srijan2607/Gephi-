# Job Graph Converter: Calculations and Structure

This document explains:

1. What the repo takes as input
2. What the repo actually calculates
3. What `mapping_similarity` means in this codebase
4. How the output graph is structured
5. Where the Python pipeline and the web/API pipeline differ

## 1. Short answer: what is `mapping_similarity`?

The field is called `mapping_similarity` in this repo, not `mapped similarity`.

In the `skills` JSON, `mapping_similarity` is a numeric score, typically between `0.0` and `1.0`, representing how strongly a skill is matched to a job posting.

Important: this repo does **not** compute that score from scratch.

It only:

- reads the score from the input JSON
- uses it to sort skills
- filters skills using `min_similarity`
- stores it on job-to-skill edges
- uses it to compute skill-level summary stats like `max_similarity` and `avg_similarity`

So if someone asks, "How exactly is `mapping_similarity` calculated?", the honest answer is:

> It is not calculated in this repository. It is already present in the input `importance_standardised` JSON, and this repo consumes it downstream.

Relevant code paths:

- `graph_builder/parser.py` reads `mapping_similarity`
- `src/app/api/process/route.ts` also reads `mapping_similarity`
- `graph_builder/graph.py` uses it for ranking, filtering, and edge weight
- `graph_builder/normalizer.py` aggregates it into `max_similarity` and `avg_similarity`

## 2. Repo structure at a glance

### Main Python pipeline

- `build_graph.py`
  - main entry point for the full graph build
- `graph_builder/config.py`
  - CLI arguments and validation
- `graph_builder/parser.py`
  - row parsing and skills JSON parsing
- `graph_builder/normalizer.py`
  - skill normalization, alias tracking, aggregation
- `graph_builder/graph.py`
  - graph construction
- `graph_builder/sampler.py`
  - optional statistical and performance sampling
- `graph_builder/exporter.py`
  - CSV and GraphML export
- `graph_builder/validator.py`
  - report generation and quality checks

### Web/API pipeline

- `src/app/api/process/route.ts`
  - lightweight web processing path
- `scripts/process-large-csv.js`
  - large-file Node.js processing path with similar logic

## 3. Input data structure

The important input field for skills is usually:

- `importance_standardised`

Expected format:

```json
[
  {
    "skill": "Python",
    "bucket": "Advanced",
    "mapping_similarity": 0.95,
    "thinking": "Strong Python skills required..."
  },
  {
    "skill": "Machine Learning",
    "bucket": "Working Knowledge",
    "mapping_similarity": 0.85
  }
]
```

Important row-level columns used by the Python pipeline:

- `Job Title`
- `Company Name`
- `District`
- `importance_standardised`
- `Assigned_Occupation_Group`
- `Group`
- `NCO Code`
- `Posted At`
- `Schedule Type`
- `Work From Home`
- `Hybrid NCO JD`
- `token_count`
- `Highest Similarity Spec`
- `Highest Similarity Score Spec`
- `salary_mean_inr_month`
- `salary_currency_unit`
- `salary_source`

Two fields that are also passthrough metadata, not computed in this repo:

- `Highest Similarity Spec`
- `Highest Similarity Score Spec`

## 4. End-to-end processing flow

The Python pipeline in `build_graph.py` runs in six phases:

1. Parse input rows
2. Normalize skills
3. Build the graph
4. Sample the graph, if requested
5. Export outputs
6. Validate and write reports

This is the authoritative, full-featured pipeline in the repo.

## 5. Calculations performed in the Python pipeline

## 5.1 Row parsing and basic coercion

Implemented mainly in `graph_builder/parser.py`.

### Job ID generation

If `job_id_column` is not provided and remains `auto`, the repo generates a deterministic job ID as:

```text
unique_key = "{Job Title}|{Company Name}|{District}|{row_idx}"
job_id = md5(unique_key)[:16]
```

So the calculation is:

```text
job_id = first 16 hex chars of md5(title | company | district | row index)
```

### Type coercion

The parser converts fields safely:

- strings through `safe_str(...)`
- floats through `safe_float(...)`
- integers through `safe_int(...)`
- booleans through `parse_boolean(...)`

For `Work From Home`, the Python pipeline converts the value into:

- `yes`
- `no`
- empty string if unknown

### Skills JSON parsing

For each skill entry, the Python parser keeps:

- `skill`
- `bucket`
- `mapping_similarity`
- `thinking`

If `mapping_similarity` is missing or invalid, it falls back to `0.0`.

## 5.2 Skill normalization and canonicalization

Implemented in `graph_builder/normalizer.py`.

The purpose is to merge similar spellings or formatting variants of the same skill into one canonical skill node.

### Normalization steps

For each raw skill label:

1. trim whitespace
2. lowercase
3. remove trailing punctuation
4. collapse repeated whitespace
5. normalize Unicode dashes to `-`
6. normalize slashes to `-`
7. normalize spaces around hyphens
8. expand a few abbreviations:
   - `&` -> `and`
   - `w/` -> `with`
   - `w/o` -> `without`

After normalization, the canonical key is created with `slugify(...)`.

Example:

```text
"Machine Learning / AI" -> "machine-learning-ai"
```

### Skip rules

A skill is skipped if:

- it is empty
- normalized length is less than `2`
- normalized length is greater than `100`
- it is numeric-only
- slugification produces an empty key

### Aggregations tracked per canonical skill

For every accepted skill occurrence:

```text
occurrence_count += 1
max_similarity = max(max_similarity, mapping_similarity)
sum_similarity += mapping_similarity
aliases.add(raw_label)
buckets.add(bucket)
```

Later, the exported skill stats use:

```text
avg_similarity = sum_similarity / occurrence_count
```

### Normalization summary metrics

The repo also computes:

```text
dedup_ratio = 1 - (canonical_skill_count / raw_skill_count)
avg_aliases_per_skill = total_aliases / canonical_skill_count
```

These go into `report.json` and `build_report.md`.

## 5.3 Graph structure

Implemented in `graph_builder/graph.py`.

The Python graph has three node types:

- `job`
- `skill`
- `category`

And two edge types:

- `REQUIRES_SKILL`
- `IN_CATEGORY`

### Job nodes

Each job node stores metadata such as:

- job title
- company name
- posting date
- schedule type
- work from home
- district
- NCO code
- group/category labels
- token count
- highest similarity spec
- highest similarity score
- salary fields
- `skill_count`

### Category nodes

Category IDs are created as:

```text
cat:{slugified assigned_occupation_group or group_name}
```

Each category node gets:

- `id`
- `label`
- `kind = category`
- `nco_code`
- `job_count`

### Skill nodes

Skill IDs are created as:

```text
skill:{canonical_key}
```

Each skill node stores:

- `id`
- `label`
- `kind = skill`
- `canonical_key`
- `aliases`
- `job_count`
- `max_similarity`
- `avg_similarity`

## 5.4 Job-to-skill edge calculation

This is where `mapping_similarity` matters most downstream.

For each job:

1. take all skills from the parsed JSON
2. sort them by `mapping_similarity` descending
3. optionally filter by bucket
4. filter out skills with `mapping_similarity < min_similarity`
5. map raw skill labels to canonical skill IDs
6. skip duplicate canonical skills within the same job
7. create one edge per surviving skill
8. stop once `top_k_skills` is reached, if `top_k_skills > 0`

Edge structure:

```text
source = job:{job_id}
target = skill:{canonical_key}
rel = REQUIRES_SKILL
bucket = original bucket
mapping_similarity = rounded similarity
weight = mapping_similarity
thinking = optional
```

The important calculation is:

```text
weight = mapping_similarity
```

Because the skills are sorted descending before duplicates are skipped, the Python pipeline effectively keeps the highest-similarity version when multiple raw labels collapse to the same canonical skill inside one job.

## 5.5 Category edge calculation

For each job with a category:

```text
source = job:{job_id}
target = cat:{category_slug}
rel = IN_CATEGORY
```

Then category counts are updated as:

```text
category.job_count = number of IN_CATEGORY edges pointing to that category
```

## 5.6 Graph summary metrics

The graph builder calculates summary metrics such as:

- total nodes
- total edges
- nodes by kind
- edges by relationship
- `jobs_with_skills_count`
- `jobs_with_skills_pct`
- `jobs_with_category_count`
- `avg_skills_per_job`
- `skills_filtered_by_similarity`
- `skills_filtered_by_bucket`

Formula used for average skills per job:

```text
avg_skills_per_job = REQUIRES_SKILL edge count / job node count
```

## 5.7 Sampling calculations

Implemented in `graph_builder/sampler.py`.

There are two sampling modes.

### Statistical sampling (`subset_mode = stats`)

This mode uses Cochran's formula for proportion estimation:

```text
n0 = (Z^2 * p * (1 - p)) / e^2
```

Where:

- `Z` = z-score for confidence level
- `p` = estimated proportion, default `0.5` in worst-case mode
- `e` = margin of error

If finite population correction is enabled:

```text
n = n0 / (1 + (n0 - 1) / N)
```

Then the sample is allocated across categories proportionally:

```text
n_h = ceil(n * (N_h / N))
```

Where:

- `N` = total jobs
- `N_h` = jobs in category `h`
- `n_h` = sample allocated to category `h`

The sampler then enforces `min_per_category`.

Important implementation note:

Although comments mention mean estimation, the current code path actually computes sample size using the Cochran proportion formula above.

### Performance sampling (`subset_mode = perf`)

This mode estimates how many jobs can fit within a target output size.

The current byte estimate is:

```text
bytes_per_job = 500
bytes_per_job += 100
bytes_per_job += avg_skills * 150
bytes_per_job += avg_skills * 20
```

Where:

- `500` is estimated job node size
- `100` is estimated category edge size
- `150` is estimated bytes per skill edge
- `20` is amortized bytes per skill node
- `avg_skills = top_k_skills` if set, otherwise `8`

Then:

```text
max_jobs = int(subset_max_bytes / bytes_per_job * 0.8)
max_jobs = max(max_jobs, 100)
```

The `0.8` factor is a safety margin.

If the eligible jobs exceed `max_jobs`, the repo samples proportionally across categories.

## 5.8 Export structure

Implemented in `graph_builder/exporter.py`.

### `nodes.csv`

Contains a union of job, skill, and category attributes.

Important columns include:

- `id`
- `label`
- `kind`
- job metadata fields
- `canonical_key`
- `aliases`
- `job_count`
- `max_similarity`
- `avg_similarity`

### `edges.csv`

Important columns include:

- `source`
- `target`
- `rel`
- `bucket`
- `mapping_similarity`
- `weight`
- `thinking` if `drop_thinking = false`

### `graph.graphml`

GraphML is exported with dynamic key generation based on actual node and edge attributes.

## 5.9 Validation and reporting

Implemented in `graph_builder/validator.py`.

The validator writes:

- `report.json`
- `build_report.md`

These include:

- input row counts
- parse failures
- normalization metrics
- graph metrics
- quality checks
- output file stats
- optional sampling report

## 6. Important difference: Python pipeline vs web/API pipeline

This repo contains two different processing styles, and they are not identical.

## 6.1 What the web/API path does

`src/app/api/process/route.ts` and `scripts/process-large-csv.js` also parse `mapping_similarity`, but they do not compute it.

They read it directly from the input JSON as:

```text
mappingSimilarity = parseFloat(item.mapping_similarity) || 0
```

## 6.2 Structural differences from the Python pipeline

### Difference 1: category edge direction

Python pipeline:

```text
job -> category
```

Web/API pipeline:

```text
category -> job
```

So `IN_CATEGORY` is reversed between the two implementations.

### Difference 2: category ID construction

Python pipeline:

```text
cat:{slugified category name}
```

Web/API pipeline:

```text
cat:nco:{NCO Code}
```

or, if no NCO code:

```text
cat:group:{normalized group name}
```

### Difference 3: job ID handling

Python pipeline:

- can auto-generate job IDs

Web/API pipeline:

- expects `Job ID`
- skips rows if `Job ID` is missing

### Difference 4: duplicate skill handling

Python pipeline:

- sorts skills by descending `mapping_similarity`
- deduplicates by canonical skill ID
- effectively keeps the highest-similarity surviving mapping per job

Web/API pipeline:

- deduplicates by normalized skill key per job
- compares bucket priority
- only replaces an existing edge if the new bucket has higher priority
- when replacement happens, it keeps the maximum of the two similarity values

So the two pipelines do not merge duplicate skills in exactly the same way.

### Difference 5: feature coverage

Python pipeline includes:

- `min_similarity`
- `top_k_skills`
- bucket filtering
- skill alias tracking
- skill-level aggregate statistics
- sampling
- report generation

Web/API pipeline is lighter and mainly focuses on producing exportable files.

## 7. Direct answer you can give someone

If someone asks what `mapping_similarity` is, the clean answer is:

> `mapping_similarity` is the match score between a skill and a job posting inside the input `importance_standardised` JSON. This repo does not calculate that score itself. It reads it from the input data, then uses it to rank skills, filter skills below a threshold, set job-to-skill edge weights, and compute aggregate skill statistics like max and average similarity.

If they ask for the exact formula:

> The exact formula is not in this repository. It must come from the upstream skill-mapping pipeline or model that generated the `importance_standardised` JSON.

## 8. File references

Useful files to inspect for this topic:

- `build_graph.py`
- `graph_builder/parser.py`
- `graph_builder/normalizer.py`
- `graph_builder/graph.py`
- `graph_builder/sampler.py`
- `graph_builder/exporter.py`
- `graph_builder/validator.py`
- `src/app/api/process/route.ts`
- `scripts/process-large-csv.js`
