# Job Graph Converter

A web application that converts job dataset CSV files (60k-80k rows) into graph format suitable for Gephi visualization and analysis.

## Features

- **CSV/Excel Support**: Upload CSV or XLSX files with job data
- **Web Worker Processing**: Handles large datasets without freezing the UI
- **Graph Generation**: Creates nodes (categories, jobs, skills) and edges
- **Multiple Export Formats**:
  - `nodes.csv` - All nodes with attributes
  - `edges.csv` - All edges with relationships
  - `graph.graphml` - GraphML format for direct Gephi import
- **Configurable Settings**:
  - Similarity threshold filter
  - Skill bucket filter
  - Salary field inclusion toggle
- **Progress Tracking**: Real-time progress updates during processing
- **Top Skills Analysis**: Shows top 10 skills by degree

## Graph Model

### Node Types

1. **Category Nodes** (`kind: "category"`)
   - ID: `cat:nco:{nco_code}` or `cat:{normalized_group_name}`
   - Attributes: nco_code, group_name

2. **Job Nodes** (`kind: "job"`)
   - ID: `job:{job_id}`
   - Attributes: job_title, company_name, posted_at, schedule_type, work_from_home, district, and more

3. **Skill Nodes** (`kind: "skill"`)
   - ID: `skill:{normalized_skill_name}`
   - Attributes: skill_name_original

### Edge Types

1. **Category → Job** (`rel: "IN_CATEGORY"`)
   - Connects job groups to jobs

2. **Job → Skill** (`rel: "REQUIRES_SKILL"`)
   - Attributes: bucket, mapping_similarity, thinking

## Quick Start

### Prerequisites

- Node.js 18+ installed
- npm or yarn package manager

### Installation

```bash
# Clone or navigate to the project
cd job-graph-converter

# Install dependencies
npm install

# Start development server
npm run dev
```

The app will be available at `http://localhost:3000`

### Usage

1. **Upload Data**: Drag and drop your CSV file or click to browse
2. **Preview**: Review detected columns and first 5 rows
3. **Configure Settings**:
   - Toggle salary fields inclusion
   - Set similarity threshold (0.0 - 1.0)
   - Select allowed skill buckets
   - Enable/disable GraphML export
4. **Generate**: Click "Generate Graph" and wait for processing
5. **Download**: Download nodes.csv, edges.csv, and optionally graph.graphml

## Input CSV Format

Required columns:
- `Job ID` - Unique job identifier
- `Job Title` - Job title
- `Group` - Job category/group
- `importance_standardised` - JSON array of skill objects

Expected skill object format:
```json
{
  "skill": "Skill Name",
  "bucket": "Proficient",
  "thinking": "Reasoning text...",
  "mapping_similarity": 0.75
}
```

Valid bucket values:
- Familiarity
- Working Knowledge
- Proficient
- Advanced
- Mission-Critical

## Importing into Gephi

### Method 1: GraphML Import (Recommended)

1. Open Gephi and create a new project
2. Go to **File → Open**
3. Select the downloaded `graph.graphml` file
4. Choose "Append to existing workspace" or "New workspace"
5. Click OK

### Method 2: CSV Import

1. Open Gephi and create a new project
2. Go to **File → Import Spreadsheet**
3. Import `nodes.csv` first:
   - Select "Nodes table"
   - Set "id" as the identifier column
4. Import `edges.csv`:
   - Select "Edges table"
   - Set "source" and "target" columns

### Visualization Tips

1. **Layout**: Use ForceAtlas2 or Fruchterman-Reingold for layout
2. **Node Sizing**: Size by degree (Ranking → Degree)
3. **Coloring**: Partition by "kind" attribute to color by node type
4. **Filtering**: Use Filters to show specific buckets or similarity ranges

## Performance Tuning

### For Large Datasets (60k+ rows)

1. **Increase Similarity Threshold**: Set to 0.5+ to reduce edge count
2. **Filter Buckets**: Only include Mission-Critical and Advanced skills
3. **Gephi Memory**: Increase Gephi's memory allocation in `gephi.conf`:
   ```
   default_options="-J-Xms512m -J-Xmx4g"
   ```

### Gephi Performance Tips

- Use "Modularity" statistic before running layouts
- Enable "Prevent overlap" only after initial layout
- Use "Adjust by Sizes" sparingly
- Consider filtering to show only high-degree nodes first

## Development

### Running Tests

```bash
npm test
```

### Building for Production

```bash
npm run build
npm start
```

### Project Structure

```
job-graph-converter/
├── src/
│   ├── app/
│   │   └── page.tsx           # Main page component
│   ├── components/
│   │   ├── FileUpload.tsx     # File upload handler
│   │   ├── Preview.tsx        # Data preview table
│   │   ├── Settings.tsx       # Configuration panel
│   │   ├── Progress.tsx       # Progress indicator
│   │   └── Results.tsx        # Download results
│   ├── lib/
│   │   ├── types.ts           # TypeScript definitions
│   │   ├── normalize.ts       # Normalization utilities
│   │   ├── graphml.ts         # GraphML generation
│   │   └── csv-export.ts      # CSV export utilities
│   ├── workers/
│   │   └── graph-worker.ts    # Web Worker for processing
│   └── __tests__/
│       └── normalize.test.ts  # Unit tests
├── public/
│   └── sample-data.csv        # Sample test data
├── package.json
└── README.md
```

## Skill Deduplication Rules

When the same skill appears multiple times for a single job:

1. **Bucket Priority**: Keep the highest priority bucket
   - Mission-Critical > Advanced > Proficient > Working Knowledge > Familiarity
2. **Similarity Score**: Keep the maximum mapping_similarity
3. **Thinking Text**: Concatenate unique thinking texts with " | " separator

## Bucket Normalization

Bucket values with numeric prefixes are normalized:
- `"1: Familiarity"` → `"Familiarity"`
- `"4: Advanced"` → `"Advanced"`

## Known Limitations

- Maximum file size depends on browser memory (typically 500MB+)
- XLSX files are converted to CSV in memory
- Very large GraphML files may be slow to load in Gephi

## Troubleshooting

### "Processing Failed" Error

1. Check that your CSV has the required columns
2. Verify the `importance_standardised` column contains valid JSON
3. Try processing a smaller subset of data first

### Gephi Won't Open GraphML

1. Check the file size (Gephi struggles with files > 100MB)
2. Increase Gephi's memory allocation
3. Try importing nodes.csv and edges.csv separately

### UI Freezes During Processing

Processing happens in a Web Worker, but very large files may cause:
1. Initial file reading delay
2. Final result aggregation delay

Wait for completion or click "Stop" to cancel.

## License

MIT License

## Sample Data

A sample CSV file is included at `public/sample-data.csv` for testing.
