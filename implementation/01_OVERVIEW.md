# Implementation Overview

## Project: Job-Skills Graph Builder v2.0

### Executive Summary

Build a robust, scalable graph builder that transforms job posting data into a proper knowledge graph with:
- **Jobs** linked to **Skills** (with proficiency buckets and similarity scores)
- **Jobs** linked to **Categories** (occupation groups)
- **Skills** properly canonicalized so overlaps exist across jobs

### Current Problems (Why Rebuild?)

| Problem | Impact | Root Cause |
|---------|--------|------------|
| 233K unique skills for 60K jobs | No meaningful skill overlap | No normalization/canonicalization |
| GraphML missing job metadata | Can't filter in Gephi | Only 4 fields exported |
| Jobs missing skill edges | Broken graph structure | Silent JSON parse failures |
| 2.1GB GraphML file | Gephi crashes | Includes all data, no lightweight mode |
| Random sampling | Not statistically valid | No stratification or sample size calculation |

### Solution Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      INPUT: CSV/Excel                           │
│  (job_id, title, company, skills_json, category, salary, ...)  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 1: PARSING                             │
│  - Load data in chunks (memory efficient)                       │
│  - Parse importance_standardised JSON                           │
│  - Log failures to bad_rows.csv                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                PHASE 2: SKILL CANONICALIZATION                  │
│  - Normalize: lowercase, strip, collapse spaces                 │
│  - Generate skill_key from normalized label                     │
│  - Build skill_dictionary: original → canonical                 │
│  - Dedupe skills across all jobs                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 3: GRAPH CONSTRUCTION                    │
│  - Create Category nodes (unique by group)                      │
│  - Create Job nodes (with FULL metadata)                        │
│  - Create Skill nodes (canonical, deduplicated)                 │
│  - Create edges: Job→Category, Job→Skill                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 4: SAMPLING (Optional)                 │
│  Mode A: Statistical sample (Cochran formula, stratified)       │
│  Mode B: Performance sample (size-bounded, graph-aware)         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PHASE 5: EXPORT                            │
│  - nodes.csv (all node types with full attributes)              │
│  - edges.csv (with rel, bucket, similarity)                     │
│  - graph.graphml (Gephi-ready)                                  │
│  - skill_dictionary.csv                                         │
│  - bad_rows.csv                                                 │
│  - report.json (metrics and validation)                         │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Python over Node.js**: Better data science libraries (pandas, scipy), easier streaming
2. **Chunk-based processing**: Handle 60K-80K rows without RAM explosion
3. **Two-pass approach**: Pass 1 builds skill dictionary, Pass 2 builds graph
4. **Configurable exports**: Full fidelity vs lightweight Gephi-friendly

### Deliverables

| Artifact | Purpose |
|----------|---------|
| `build_graph.py` | Main CLI script |
| `graph_builder/` | Python package with modules |
| `nodes.csv` | All nodes with attributes |
| `edges.csv` | All edges with attributes |
| `graph.graphml` | Gephi import file |
| `skill_dictionary.csv` | Skill normalization mapping |
| `bad_rows.csv` | Failed rows with reasons |
| `report.json` | Validation metrics |
| `README.md` | Usage documentation |

### Timeline/Phases

1. **Planning** (this document set) - Define everything before coding
2. **Core Builder** - Parsing, canonicalization, graph construction
3. **Export Module** - CSV, GraphML, lightweight modes
4. **Sampling Module** - Statistical and performance sampling
5. **Validation** - Tests and verification
6. **Documentation** - README and examples
