# Problem Analysis: What Went Wrong

## Current State Analysis

### Issue 1: Skill Explosion (233K unique skills)

**Symptom**: 233,093 unique skill nodes for ~60K jobs
**Expected**: ~5,000-15,000 unique skills with heavy overlap

**Root Cause Analysis**:
```
Current logic:
  skill_id = "skill:" + slugify(skill_label)

Problem: No normalization before slugification
```

**Evidence of the problem**:
```
These are treated as DIFFERENT skills:
- "Python"
- "python"
- "Python "
- "PYTHON"
- "Python."
- "python programming"
- "Python Programming"

These should be ONE skill: "python"
```

**Why this kills the graph**:
- Graph theory: A bipartite job-skill graph's value comes from SHARED skills
- If every skill is unique, the graph is just disconnected star patterns
- No community detection possible, no skill clustering, no overlap analysis

---

### Issue 2: Missing Job Metadata in GraphML

**Symptom**: GraphML only has 4 node attributes: label, kind, nco_code, group_name
**Expected**: 15+ job attributes for filtering in Gephi

**Root Cause**:
```javascript
// Current generate-minimal-graphml.js line 105:
graphml.write(`<node id="..."><data key="label">...</data><data key="kind">...</data><data key="nco_code">...</data><data key="group_name">...</data></node>`);

// Missing: company, district, salary, posted_at, schedule, wfh, etc.
```

**Impact**:
- Cannot filter jobs by company in Gephi
- Cannot analyze salary distribution across skill clusters
- Cannot segment by geography (district)
- Cannot analyze temporal patterns (posted_at)

---

### Issue 3: Silent Edge Dropping

**Symptom**: Many jobs have no skill edges despite having importance_standardised data
**Expected**: Every job with valid JSON should have skill edges

**Root Cause**: Multiple failure modes not logged:

```javascript
// Potential silent failures:
1. JSON.parse() fails on malformed importance_standardised → no error logged
2. Empty array after parse → no edges, no warning
3. Missing "skill" key in dict → edge skipped silently
4. skill_label is empty/null → edge skipped
```

**Evidence**:
- 596K jobs in data
- 4.6M edges
- Average 7.7 edges per job
- But: standard job postings have 10-20 skills
- Suggests ~30-50% of skill data is being lost

---

### Issue 4: GraphML File Size (2.1GB)

**Symptom**: 2.1GB file crashes Gephi on most machines
**Root Cause**: Including ALL data for ALL nodes/edges

**Breakdown**:
```
829K nodes × ~500 bytes average = ~400MB for nodes
4.6M edges × ~400 bytes average = ~1.8GB for edges
Total ≈ 2.2GB (matches observed)
```

**Solutions needed**:
1. Lightweight export mode (drop verbose fields like "thinking")
2. Edge filtering (min_similarity threshold)
3. Top-K skills per job option
4. Sampling for manageable subsets

---

### Issue 5: Non-Statistical Sampling

**Symptom**: Random sampling without stratification or sample size justification
**Expected**: Statistically valid sample for inference

**Current approach**:
```javascript
// Random shuffle, take first N
const shuffledJobs = jobs.sort(() => Math.random() - 0.5);
shuffledJobs.slice(0, jobSampleSize)
```

**Problems**:
1. No stratification by category → may miss rare categories entirely
2. No sample size calculation → arbitrary numbers (10K, 50K)
3. No confidence interval or margin of error consideration
4. No reproducibility (no seed)

---

## Quantified Impact

| Metric | Current | Expected After Fix |
|--------|---------|-------------------|
| Unique skills | 233,093 | ~8,000-15,000 |
| Skill overlap ratio | ~0% | 60-80% |
| Job attributes in GraphML | 4 | 15+ |
| Jobs with skill edges | ~70% | 98%+ |
| Bad rows logged | 0 | All failures |
| Gephi-loadable file size | 2.1GB (crashes) | <100MB option |
| Sample statistical validity | None | 95% CI, 3% margin |

---

## Technical Debt Inventory

1. **No Python tooling**: Current implementation is Node.js only
2. **No streaming**: Loads entire dataset into memory
3. **No validation**: No assertions or quality checks
4. **No testing**: No unit tests for edge cases
5. **No documentation**: No README for CLI usage
6. **Hardcoded paths**: Not configurable

---

## Success Criteria for v2.0

1. ✅ Skill count drops by 90%+ (from 233K to <25K)
2. ✅ Every valid job has skill edges (>98%)
3. ✅ All job metadata in exports
4. ✅ Gephi-loadable files (<100MB option)
5. ✅ Statistical sampling with documented methodology
6. ✅ Bad rows logged with reasons
7. ✅ Reproducible with seeds
8. ✅ CLI with all options documented
