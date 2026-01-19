# Graph Schema Definition

## Node Types

### 1. Category Node

Represents an occupation group/category.

```yaml
Category:
  id: "cat:{slug}"                    # e.g., "cat:textile-fur-leather-operators"
  attributes:
    label: string                     # Display name
    kind: "category"                  # Fixed value
    nco_code: string                  # NCO code if available (e.g., "815")
    job_count: integer                # Number of jobs in this category (computed)
```

**ID Generation**:
```python
def category_id(group_name: str) -> str:
    slug = slugify(group_name.lower().strip())
    return f"cat:{slug}"
```

---

### 2. Job Node

Represents a single job posting with full metadata.

```yaml
Job:
  id: "job:{job_id}"                  # e.g., "job:abc123" or "job:{hash}"
  attributes:
    # Required
    label: string                     # Job title (for Gephi display)
    kind: "job"                       # Fixed value

    # Core metadata
    job_title: string                 # Full job title
    company_name: string              # Employer name
    posted_at: string                 # ISO date or original format

    # Work arrangement
    schedule_type: string             # "Full-time", "Part-time", etc.
    work_from_home: string            # "yes", "no", "hybrid", or blank
    district: string                  # Location

    # Classification
    nco_code: string                  # NCO occupation code
    group_name: string                # Occupation group
    assigned_occupation_group: string # Alternative grouping

    # Technical metadata
    hybrid_nco_jd: string             # Hybrid NCO job description
    token_count: integer              # Token count from NLP
    highest_similarity_spec: string   # Best matching specification
    highest_similarity_score: float   # Similarity score

    # Salary
    salary_mean_inr_month: float      # Monthly salary in INR
    salary_currency_unit: string      # Currency (INR, USD, etc.)
    salary_source: string             # "system", "derived", or blank

    # Stats (computed)
    skill_count: integer              # Number of skills for this job
```

**ID Generation**:
```python
def job_id(row: dict) -> str:
    # If explicit job_id column exists, use it
    if row.get('job_id'):
        return f"job:{row['job_id']}"

    # Otherwise, create deterministic hash from unique combo
    unique_key = f"{row['job_title']}|{row['company_name']}|{row['district']}"
    hash_val = hashlib.md5(unique_key.encode()).hexdigest()[:12]
    return f"job:{hash_val}"
```

---

### 3. Skill Node

Represents a canonicalized skill.

```yaml
Skill:
  id: "skill:{canonical_key}"         # e.g., "skill:python-programming"
  attributes:
    label: string                     # Canonical display label
    kind: "skill"                     # Fixed value
    canonical_key: string             # Normalized key used for deduplication
    aliases: string                   # Pipe-separated original variants
    job_count: integer                # Number of jobs requiring this skill (computed)
    avg_similarity: float             # Average mapping_similarity across jobs
```

**ID Generation** (CRITICAL for deduplication):
```python
def normalize_skill(raw_skill: str) -> str:
    """
    Normalize skill label to canonical form.
    This is the KEY function that enables skill overlap.
    """
    s = raw_skill.strip()
    s = s.lower()

    # Remove trailing punctuation
    s = re.sub(r'[.,:;!?]+$', '', s)

    # Normalize whitespace
    s = re.sub(r'\s+', ' ', s)

    # Normalize dashes and slashes
    s = s.replace('–', '-').replace('—', '-')  # em/en dash to hyphen
    s = re.sub(r'\s*[-/]\s*', '-', s)          # normalize around dashes/slashes

    # Remove parenthetical clarifications for matching
    # But keep them in aliases
    # s = re.sub(r'\s*\([^)]*\)', '', s)  # Optional: remove (...)

    # Common abbreviation normalization
    s = re.sub(r'\bw/\b', 'with', s)
    s = re.sub(r'\b&\b', 'and', s)

    return s.strip()

def skill_key(raw_skill: str) -> str:
    """Generate the canonical key used for skill ID."""
    normalized = normalize_skill(raw_skill)
    return slugify(normalized)

def skill_id(raw_skill: str) -> str:
    return f"skill:{skill_key(raw_skill)}"
```

---

## Edge Types

### 1. Job → Category Edge

```yaml
IN_CATEGORY:
  source: job node id
  target: category node id
  attributes:
    rel: "IN_CATEGORY"                # Relationship type
```

**Creation Rule**: One edge per job to its primary category.

---

### 2. Job → Skill Edge

```yaml
REQUIRES_SKILL:
  source: job node id
  target: skill node id
  attributes:
    rel: "REQUIRES_SKILL"             # Relationship type
    bucket: string                    # Proficiency level:
                                      # "Familiarity", "Working Knowledge",
                                      # "Proficient", "Advanced", "Mission-Critical"
    mapping_similarity: float         # 0.0 to 1.0
    thinking: string                  # (OPTIONAL - omit in lightweight export)
    weight: float                     # = mapping_similarity (for Gephi)
```

**Creation Rule**: One edge per skill in the job's importance_standardised array.

---

## GraphML Attribute Definitions

```xml
<!-- Node attributes -->
<key id="label" for="node" attr.name="label" attr.type="string"/>
<key id="kind" for="node" attr.name="kind" attr.type="string"/>

<!-- Job-specific attributes -->
<key id="job_title" for="node" attr.name="job_title" attr.type="string"/>
<key id="company_name" for="node" attr.name="company_name" attr.type="string"/>
<key id="posted_at" for="node" attr.name="posted_at" attr.type="string"/>
<key id="schedule_type" for="node" attr.name="schedule_type" attr.type="string"/>
<key id="work_from_home" for="node" attr.name="work_from_home" attr.type="string"/>
<key id="district" for="node" attr.name="district" attr.type="string"/>
<key id="nco_code" for="node" attr.name="nco_code" attr.type="string"/>
<key id="group_name" for="node" attr.name="group_name" attr.type="string"/>
<key id="salary_mean" for="node" attr.name="salary_mean_inr_month" attr.type="double"/>
<key id="salary_source" for="node" attr.name="salary_source" attr.type="string"/>
<key id="skill_count" for="node" attr.name="skill_count" attr.type="int"/>

<!-- Skill-specific attributes -->
<key id="canonical_key" for="node" attr.name="canonical_key" attr.type="string"/>
<key id="aliases" for="node" attr.name="aliases" attr.type="string"/>
<key id="job_count" for="node" attr.name="job_count" attr.type="int"/>

<!-- Edge attributes -->
<key id="rel" for="edge" attr.name="rel" attr.type="string"/>
<key id="bucket" for="edge" attr.name="bucket" attr.type="string"/>
<key id="similarity" for="edge" attr.name="mapping_similarity" attr.type="double"/>
<key id="weight" for="edge" attr.name="weight" attr.type="double"/>
```

---

## Data Flow Example

**Input Row**:
```json
{
  "Job Title": "Python Developer",
  "Company Name": "TechCorp",
  "District": "Bangalore, Karnataka",
  "Assigned_Occupation_Group": "Software Developers",
  "importance_standardised": "[{\"skill\":\"Python\",\"bucket\":\"Advanced\",\"mapping_similarity\":0.92},{\"skill\":\"python programming\",\"bucket\":\"Proficient\",\"mapping_similarity\":0.85}]"
}
```

**After Processing**:

Nodes:
```
cat:software-developers     | kind=category | label="Software Developers"
job:abc123                  | kind=job      | label="Python Developer" | company_name="TechCorp" | ...
skill:python                | kind=skill    | label="Python" | aliases="Python|python programming"
```

Edges:
```
job:abc123 → cat:software-developers  | rel=IN_CATEGORY
job:abc123 → skill:python             | rel=REQUIRES_SKILL | bucket=Advanced | mapping_similarity=0.92
```

Note: "Python" and "python programming" are MERGED into one skill node "skill:python" because they normalize to the same key.
