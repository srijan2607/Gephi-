# Skill Canonicalization Strategy

## The Core Problem

**Input**: 233,093 unique skill strings across ~60K jobs
**Goal**: Reduce to ~8,000-15,000 canonical skills with meaningful overlap

## Canonicalization Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                   RAW SKILL STRING                          │
│            "  Python Programming.  "                        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 1: BASIC NORMALIZATION                    │
│  - Strip whitespace                                         │
│  - Lowercase                                                │
│  - Remove trailing punctuation                              │
│  Result: "python programming"                               │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 2: WHITESPACE NORMALIZATION               │
│  - Collapse multiple spaces                                 │
│  - Normalize around punctuation                             │
│  Result: "python programming"                               │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 3: CHARACTER NORMALIZATION                │
│  - Convert em/en dashes to hyphens                          │
│  - Normalize slashes to hyphens                             │
│  - Expand common abbreviations (& → and, w/ → with)         │
│  Result: "python programming"                               │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 4: GENERATE CANONICAL KEY                 │
│  - Slugify for ID-safe string                               │
│  Result: "python-programming"                               │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              STEP 5: MERGE & TRACK ALIASES                  │
│  - Look up existing skill by canonical_key                  │
│  - If exists: add original as alias, use highest similarity │
│  - If new: create new skill entry                           │
│  Result: skill:python-programming with alias tracking       │
└─────────────────────────────────────────────────────────────┘
```

## Normalization Rules (Detailed)

### Rule 1: Whitespace Handling
```python
# Before: "  Machine   Learning  "
# After:  "machine learning"

s = s.strip()
s = re.sub(r'\s+', ' ', s)
```

### Rule 2: Case Normalization
```python
# Before: "PYTHON", "Python", "python"
# After:  "python" (all three)

s = s.lower()
```

### Rule 3: Trailing Punctuation Removal
```python
# Before: "Python.", "Excel,", "Data Analysis;"
# After:  "python", "excel", "data analysis"

s = re.sub(r'[.,:;!?]+$', '', s)
```

### Rule 4: Dash/Slash Normalization
```python
# Before: "front-end", "front–end", "front—end", "front / end"
# After:  "front-end" (all become same)

s = s.replace('–', '-').replace('—', '-')  # Unicode dashes
s = re.sub(r'\s*/\s*', '-', s)             # Slashes to hyphens
s = re.sub(r'\s*-\s*', '-', s)             # Normalize dash spacing
```

### Rule 5: Common Abbreviation Expansion
```python
# Before: "R&D", "w/ clients"
# After:  "r and d", "with clients"

s = re.sub(r'\b&\b', ' and ', s)
s = re.sub(r'\bw/\b', 'with ', s)
s = re.sub(r'\bw/o\b', 'without ', s)
```

### Rule 6: Parenthetical Handling (Configurable)
```python
# Option A: Remove parentheticals
# "Python (programming language)" → "python"

# Option B: Keep parentheticals (default - more conservative)
# "Python (programming language)" → "python-programming-language"

# We use Option B by default to avoid false merges
```

## Skill Dictionary Structure

```python
skill_dictionary = {
    "python-programming": {
        "canonical_key": "python-programming",
        "canonical_label": "Python Programming",  # First occurrence, title-cased
        "aliases": ["Python Programming", "python programming", "PYTHON PROGRAMMING"],
        "first_seen_similarity": 0.85,
        "max_similarity": 0.92,
        "occurrence_count": 1547
    },
    ...
}
```

## Output: skill_dictionary.csv

```csv
skill_id,canonical_key,canonical_label,aliases,occurrence_count,max_similarity
skill:python-programming,python-programming,Python Programming,"Python Programming|python programming|PYTHON PROGRAMMING",1547,0.92
skill:data-analysis,data-analysis,Data Analysis,"Data Analysis|data analysis|Data analysis",2341,0.88
...
```

## Edge Case Handling

### Case 1: Empty/Null Skills
```python
if not raw_skill or raw_skill.strip() == '':
    log_warning("Empty skill encountered", job_id)
    continue  # Skip this skill, don't fail
```

### Case 2: Very Short Skills
```python
if len(normalized) < 2:
    log_warning(f"Skill too short: '{raw_skill}'", job_id)
    continue  # Skip single-letter "skills"
```

### Case 3: Very Long Skills (Likely Descriptions)
```python
if len(normalized) > 100:
    log_warning(f"Skill too long (likely description): '{raw_skill[:50]}...'", job_id)
    # Truncate or skip based on config
```

### Case 4: Numeric-Only Skills
```python
if re.match(r'^[\d\s.,-]+$', normalized):
    log_warning(f"Numeric skill skipped: '{raw_skill}'", job_id)
    continue
```

### Case 5: Duplicate Skills in Same Job
```python
# If same job has "Python" and "python programming", they map to same skill
# Keep the edge with HIGHER mapping_similarity
job_skills_seen = set()
for skill_entry in job_skills:
    canonical = skill_key(skill_entry['skill'])
    if canonical in job_skills_seen:
        # Duplicate - update if higher similarity
        continue
    job_skills_seen.add(canonical)
```

## Expected Deduplication Ratios

Based on typical job posting data:

| Category | Raw Count | After Dedup | Ratio |
|----------|-----------|-------------|-------|
| Programming languages | 5000+ variants | ~50 canonical | 99% reduction |
| Soft skills | 10000+ variants | ~200 canonical | 98% reduction |
| Tools/Software | 20000+ variants | ~2000 canonical | 90% reduction |
| Domain skills | 50000+ variants | ~5000 canonical | 90% reduction |
| **Total** | **233,000** | **~8,000-15,000** | **93-96%** |

## Validation Metrics

After canonicalization, verify:

```python
# 1. Deduplication achieved
assert unique_skills_after < unique_skills_before * 0.15  # At least 85% reduction

# 2. No empty canonical keys
assert all(s.canonical_key for s in skills)

# 3. Aliases properly tracked
total_aliases = sum(len(s.aliases) for s in skills)
assert total_aliases >= unique_skills_before * 0.9  # Most originals tracked

# 4. Top skills have high overlap
top_10_skills = sorted(skills, key=lambda s: s.occurrence_count, reverse=True)[:10]
assert all(s.occurrence_count > 1000 for s in top_10_skills)  # Common skills are common
```

## Advanced: Future Enhancements (Not v2.0)

1. **Embedding-based clustering**: Use sentence transformers to cluster similar skills
2. **Synonym dictionaries**: Manual mappings like "ML" → "machine learning"
3. **Skill hierarchies**: "Python" is-a "Programming Language"
4. **Fuzzy matching**: Levenshtein distance for typo correction

These are OUT OF SCOPE for v2.0 but the architecture should not preclude them.
