import { NextRequest, NextResponse } from 'next/server';
import { createWriteStream, createReadStream, existsSync, mkdirSync, unlinkSync, writeFileSync, promises as fsPromises } from 'fs';
import { createInterface } from 'readline';
import path from 'path';
import * as XLSX from 'xlsx';

// Helper to wait for stream to finish
function streamFinished(stream: NodeJS.WritableStream): Promise<void> {
  return new Promise((resolve, reject) => {
    stream.on('finish', resolve);
    stream.on('error', reject);
  });
}

// Normalization functions
function normalizeKey(s: string | null | undefined): string {
  if (s === null || s === undefined) return '';
  return s.toLowerCase().trim()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\s/g, '-');
}

function normalizeBucket(bucket: string): { normalized: string; raw?: string } {
  if (!bucket) return { normalized: 'unknown' };

  const CANONICAL_BUCKETS: Record<string, string> = {
    'familiarity': 'Familiarity',
    'working knowledge': 'Working Knowledge',
    'proficient': 'Proficient',
    'advanced': 'Advanced',
    'mission-critical': 'Mission-Critical',
  };

  const cleaned = bucket.replace(/^\d+:\s*/, '').trim().toLowerCase();
  return {
    normalized: CANONICAL_BUCKETS[cleaned] || bucket.trim(),
    raw: bucket
  };
}

const BUCKET_PRIORITY: Record<string, number> = {
  'Mission-Critical': 5,
  'Advanced': 4,
  'Proficient': 3,
  'Working Knowledge': 2,
  'Familiarity': 1,
};

function getBucketPriority(bucket: string): number {
  const { normalized } = normalizeBucket(bucket);
  return BUCKET_PRIORITY[normalized] || 0;
}

function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  result.push(current.trim());
  return result;
}

function parseImportanceStandardised(value: string): { skills: Array<{ skill: string; bucket: string; thinking: string; mappingSimilarity: number }>; error?: string } {
  if (!value || value === '-' || value === 'null') {
    return { skills: [] };
  }
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) {
      return { skills: [], error: 'Not an array' };
    }
    return {
      skills: parsed.map((item: Record<string, unknown>) => ({
        skill: String(item.skill || ''),
        bucket: String(item.bucket || ''),
        thinking: String(item.thinking || ''),
        mappingSimilarity: parseFloat(String(item.mapping_similarity)) || 0,
      }))
    };
  } catch {
    return { skills: [], error: 'Parse error' };
  }
}

function escapeCsv(value: unknown): string {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function escapeXml(str: unknown): string {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

export async function POST(request: NextRequest) {
  const tempFilePath = path.join(process.cwd(), 'tmp', `upload-${Date.now()}.csv`);

  try {
    const formData = await request.formData();
    const file = formData.get('file') as File | null;

    if (!file) {
      return NextResponse.json({ error: 'No file provided' }, { status: 400 });
    }

    const fileName = file.name.toLowerCase();
    const isExcel = fileName.endsWith('.xlsx') || fileName.endsWith('.xls');
    const fileSizeMB = file.size / (1024 * 1024);

    console.log(`Processing file: ${file.name}, size: ${fileSizeMB.toFixed(1)} MB, type: ${isExcel ? 'Excel' : 'CSV'}`);

    // Reject very large files to prevent memory issues
    const MAX_FILE_SIZE_MB = 100;
    if (fileSizeMB > MAX_FILE_SIZE_MB) {
      return NextResponse.json({
        error: `File is too large (${fileSizeMB.toFixed(0)} MB). For files over ${MAX_FILE_SIZE_MB}MB, use the CLI script instead:\n\nnode scripts/process-large-csv.js "your-file.csv" ./public/output`,
        suggestion: 'cli'
      }, { status: 400 });
    }

    // Ensure directories exist
    const tmpDir = path.join(process.cwd(), 'tmp');
    const outputDir = path.join(process.cwd(), 'public', 'output');
    if (!existsSync(tmpDir)) mkdirSync(tmpDir, { recursive: true });
    if (!existsSync(outputDir)) mkdirSync(outputDir, { recursive: true });

    // Handle Excel files (must be under 200MB)
    if (isExcel) {
      if (fileSizeMB > 200) {
        return NextResponse.json({
          error: `Excel file is too large (${fileSizeMB.toFixed(0)} MB). Please convert to CSV using Excel's "Save As" feature.`
        }, { status: 400 });
      }

      const buffer = await file.arrayBuffer();
      const workbook = XLSX.read(new Uint8Array(buffer), { type: 'array' });

      if (!workbook.SheetNames?.length) {
        return NextResponse.json({ error: 'No sheets found in Excel file' }, { status: 400 });
      }

      const worksheet = workbook.Sheets[workbook.SheetNames[0]];
      if (!worksheet) {
        return NextResponse.json({ error: 'Could not read worksheet. Please convert to CSV.' }, { status: 400 });
      }

      const csvContent = XLSX.utils.sheet_to_csv(worksheet);
      writeFileSync(tempFilePath, csvContent, 'utf8');
    } else {
      // For CSV: Stream the file to disk in chunks to avoid memory issues
      const writeStream = createWriteStream(tempFilePath);
      const reader = file.stream().getReader();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        writeStream.write(Buffer.from(value));
      }

      await new Promise<void>((resolve, reject) => {
        writeStream.on('finish', resolve);
        writeStream.on('error', reject);
        writeStream.end();
      });
    }

    console.log(`File saved to ${tempFilePath}, starting processing...`);

    // Process using streaming
    const nodes = new Map<string, Record<string, unknown>>();
    const edges: Array<Record<string, unknown>> = [];
    const skillMap = new Map<string, Record<string, unknown>>();

    let headers: string[] | null = null;
    let rowCount = 0;

    const fileStream = createReadStream(tempFilePath, { encoding: 'utf8' });
    const rl = createInterface({ input: fileStream, crlfDelay: Infinity });

    for await (const line of rl) {
      if (!line.trim()) continue;

      if (!headers) {
        headers = parseCSVLine(line);
        console.log(`Found ${headers.length} columns`);
        continue;
      }

      rowCount++;
      if (rowCount % 50000 === 0) {
        console.log(`Processed ${rowCount.toLocaleString()} rows...`);
      }

      const values = parseCSVLine(line);
      const row: Record<string, string> = {};
      headers.forEach((h, i) => { row[h] = values[i] || ''; });

      const jobId = row['Job ID'] || '';
      const jobTitle = row['Job Title'] || '';
      const companyName = row['Company Name'] || '';
      const postedAt = row['Posted At'] || '';
      const scheduleType = row['Schedule Type'] || '';
      const workFromHome = row['Work From Home'] || '';
      const district = row['District'] || '';
      const hybridNcoJd = row['Hybrid NCO JD'] || '';
      const ncoCode = row['NCO Code'] || '';
      const groupName = row['Group'] || '';
      const importanceStd = row['importance_standardised'] || '';
      const tokenCount = row['token_count'] || '';
      const highestSimilaritySpec = row['Highest Similarity Spec'] || '';
      const highestSimilarityScore = row['Highest Similarity Score Spec'] || '';
      const assignedOccupationGroup = row['Assigned_Occupation_Group'] || '';
      const salaryMean = row['salary_mean_inr_month'] || '';
      const salaryCurrency = row['salary_currency_unit'] || '';
      const salarySource = row['salary_source'] || '';

      if (!jobId) continue;

      // Category node
      const categoryId = ncoCode ? `cat:nco:${ncoCode}` : `cat:group:${normalizeKey(groupName)}`;
      if (!nodes.has(categoryId)) {
        nodes.set(categoryId, {
          id: categoryId,
          label: groupName || `NCO ${ncoCode}`,
          kind: 'category',
          ncoCode,
          groupName,
        });
      }

      // Job node
      const jobNodeId = `job:${jobId}`;
      if (!nodes.has(jobNodeId)) {
        nodes.set(jobNodeId, {
          id: jobNodeId, label: jobTitle, kind: 'job',
          ncoCode, groupName, jobId, jobTitle, companyName, postedAt, scheduleType,
          workFromHome: workFromHome === 'true', district, hybridNcoJd, tokenCount,
          highestSimilaritySpec, highestSimilarityScore, assignedOccupationGroup,
          salaryMean, salaryCurrency, salarySource,
        });

        edges.push({ source: categoryId, target: jobNodeId, type: 'DIRECTED', rel: 'IN_CATEGORY' });
      }

      // Parse skills
      const { skills } = parseImportanceStandardised(importanceStd);

      for (const skillEntry of skills) {
        const skillId = `skill:${normalizeKey(skillEntry.skill)}`;
        const { normalized: normalizedBucket } = normalizeBucket(skillEntry.bucket);

        if (!nodes.has(skillId)) {
          nodes.set(skillId, { id: skillId, label: skillEntry.skill, kind: 'skill', skillNameOriginal: skillEntry.skill });
        }

        const edgeKey = `${jobNodeId}:${skillId}`;
        const existing = skillMap.get(edgeKey);

        if (!existing) {
          skillMap.set(edgeKey, {
            source: jobNodeId, target: skillId, type: 'DIRECTED', rel: 'REQUIRES_SKILL',
            bucket: normalizedBucket, mappingSimilarity: skillEntry.mappingSimilarity, thinking: skillEntry.thinking,
          });
        } else {
          const existingPriority = getBucketPriority(String(existing.bucket));
          const newPriority = getBucketPriority(normalizedBucket);
          if (newPriority > existingPriority) {
            existing.bucket = normalizedBucket;
            existing.mappingSimilarity = Math.max(Number(existing.mappingSimilarity), skillEntry.mappingSimilarity);
          }
        }
      }
    }

    // Add skill edges
    for (const edge of skillMap.values()) {
      edges.push(edge);
    }

    console.log(`Processing complete: ${rowCount} rows, ${nodes.size} nodes, ${edges.length} edges`);

    // Count by type
    let categories = 0, jobs = 0, skillsCount = 0;
    for (const node of nodes.values()) {
      if (node.kind === 'category') categories++;
      else if (node.kind === 'job') jobs++;
      else if (node.kind === 'skill') skillsCount++;
    }

    // Clean up existing output files first to prevent appending
    const nodesPath = path.join(outputDir, 'nodes.csv');
    const edgesPath = path.join(outputDir, 'edges.csv');
    const graphmlPath = path.join(outputDir, 'graph.graphml');

    try {
      if (existsSync(nodesPath)) unlinkSync(nodesPath);
      if (existsSync(edgesPath)) unlinkSync(edgesPath);
      if (existsSync(graphmlPath)) unlinkSync(graphmlPath);
    } catch {
      // Ignore deletion errors
    }

    // Write nodes.csv
    console.log('Writing nodes.csv...');
    const nodeColumns = ['id', 'label', 'kind', 'nco_code', 'group_name', 'job_id', 'job_title', 'company_name', 'posted_at', 'schedule_type', 'work_from_home', 'district', 'hybrid_nco_jd', 'token_count', 'highest_similarity_spec', 'highest_similarity_score_spec', 'assigned_occupation_group', 'salary_mean_inr_month', 'salary_currency_unit', 'salary_source', 'skill_name_original'];
    const nodesFile = createWriteStream(nodesPath);
    nodesFile.write(nodeColumns.join(',') + '\n');
    for (const node of nodes.values()) {
      const row = [
        node.id, node.label, node.kind, node.ncoCode || '', node.groupName || '',
        node.jobId || '', node.jobTitle || '', node.companyName || '', node.postedAt || '',
        node.scheduleType || '', node.workFromHome || '', node.district || '',
        node.hybridNcoJd || '', node.tokenCount || '', node.highestSimilaritySpec || '',
        node.highestSimilarityScore || '', node.assignedOccupationGroup || '',
        node.salaryMean || '', node.salaryCurrency || '', node.salarySource || '',
        node.skillNameOriginal || ''
      ].map(escapeCsv);
      nodesFile.write(row.join(',') + '\n');
    }
    nodesFile.end();

    // Write edges.csv
    console.log('Writing edges.csv...');
    const edgeColumns = ['source', 'target', 'type', 'rel', 'bucket', 'mapping_similarity', 'thinking'];
    const edgesFile = createWriteStream(edgesPath);
    edgesFile.write(edgeColumns.join(',') + '\n');
    for (const edge of edges) {
      const row = [edge.source, edge.target, edge.type, edge.rel, edge.bucket || '', edge.mappingSimilarity || '', edge.thinking || ''].map(escapeCsv);
      edgesFile.write(row.join(',') + '\n');
    }
    edgesFile.end();

    // Only generate GraphML for smaller files (< 50K nodes) to avoid memory issues
    const generateGraphml = nodes.size < 50000;

    if (generateGraphml) {
      // Write graph.graphml
      console.log('Writing graph.graphml...');
      const graphmlFile = createWriteStream(graphmlPath);
      graphmlFile.write(`<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="label" for="node" attr.name="label" attr.type="string"/>
  <key id="kind" for="node" attr.name="kind" attr.type="string"/>
  <key id="nco_code" for="node" attr.name="nco_code" attr.type="string"/>
  <key id="group_name" for="node" attr.name="group_name" attr.type="string"/>
  <key id="job_title" for="node" attr.name="job_title" attr.type="string"/>
  <key id="company_name" for="node" attr.name="company_name" attr.type="string"/>
  <key id="skill_name" for="node" attr.name="skill_name" attr.type="string"/>
  <key id="rel" for="edge" attr.name="rel" attr.type="string"/>
  <key id="bucket" for="edge" attr.name="bucket" attr.type="string"/>
  <key id="mapping_similarity" for="edge" attr.name="mapping_similarity" attr.type="double"/>
  <graph id="G" edgedefault="directed">
`);

      for (const node of nodes.values()) {
        graphmlFile.write(`    <node id="${escapeXml(node.id)}">
      <data key="label">${escapeXml(node.label)}</data>
      <data key="kind">${escapeXml(node.kind)}</data>
      <data key="nco_code">${escapeXml(node.ncoCode || '')}</data>
      <data key="group_name">${escapeXml(node.groupName || '')}</data>
      <data key="job_title">${escapeXml(node.jobTitle || '')}</data>
      <data key="company_name">${escapeXml(node.companyName || '')}</data>
      <data key="skill_name">${escapeXml(node.skillNameOriginal || '')}</data>
    </node>
`);
      }

      let edgeId = 0;
      for (const edge of edges) {
        graphmlFile.write(`    <edge id="e${edgeId++}" source="${escapeXml(edge.source)}" target="${escapeXml(edge.target)}">
      <data key="rel">${escapeXml(edge.rel)}</data>
      <data key="bucket">${escapeXml(edge.bucket || '')}</data>
      <data key="mapping_similarity">${edge.mappingSimilarity || 0}</data>
    </edge>
`);
      }

      graphmlFile.write(`  </graph>
</graphml>
`);
      graphmlFile.end();

      // Wait for all streams to finish writing
      console.log('Waiting for files to finish writing...');
      await Promise.all([
        streamFinished(nodesFile),
        streamFinished(edgesFile),
        streamFinished(graphmlFile)
      ]);
    } else {
      console.log('Skipping GraphML generation for large dataset (use CSV import in Gephi)');
      // Wait for CSV streams to finish
      await Promise.all([
        streamFinished(nodesFile),
        streamFinished(edgesFile)
      ]);
    }

    // Clean up temp file
    try {
      unlinkSync(tempFilePath);
    } catch {
      // Ignore cleanup errors
    }

    console.log('Done!');

    return NextResponse.json({
      success: true,
      stats: { rows: rowCount, nodes: nodes.size, edges: edges.length, categories, jobs, skills: skillsCount },
      files: {
        nodes: '/output/nodes.csv',
        edges: '/output/edges.csv',
        graphml: generateGraphml ? '/output/graph.graphml' : null
      },
      largeDataset: !generateGraphml
    });
  } catch (error) {
    // Clean up temp file on error
    try {
      if (existsSync(tempFilePath)) unlinkSync(tempFilePath);
    } catch {
      // Ignore cleanup errors
    }

    console.error('Processing error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}

// Next.js App Router config
export const dynamic = 'force-dynamic';
export const maxDuration = 300;
