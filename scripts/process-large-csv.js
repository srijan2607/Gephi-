#!/usr/bin/env node

/**
 * CLI script to process large CSV files directly
 * Bypasses browser upload limitations
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');

// Parse command line args
const args = process.argv.slice(2);
if (args.length === 0) {
  console.log('Usage: node scripts/process-large-csv.js <input.csv> [output-dir]');
  console.log('Example: node scripts/process-large-csv.js data.csv ./output');
  process.exit(1);
}

const inputFile = args[0];
const outputDir = args[1] || './output';

// Ensure output directory exists
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

// Normalization functions
function normalizeKey(s) {
  if (s === null || s === undefined) return '';
  return s.toLowerCase().trim()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\s/g, '-');
}

function normalizeBucket(bucket) {
  if (!bucket) return { normalized: 'unknown' };

  const CANONICAL_BUCKETS = {
    'familiarity': 'Familiarity',
    'working knowledge': 'Working Knowledge',
    'proficient': 'Proficient',
    'advanced': 'Advanced',
    'mission-critical': 'Mission-Critical',
  };

  let cleaned = bucket.replace(/^\d+:\s*/, '').trim().toLowerCase();
  return {
    normalized: CANONICAL_BUCKETS[cleaned] || bucket.trim(),
    raw: bucket
  };
}

const BUCKET_PRIORITY = {
  'Mission-Critical': 5,
  'Advanced': 4,
  'Proficient': 3,
  'Working Knowledge': 2,
  'Familiarity': 1,
};

function getBucketPriority(bucket) {
  const { normalized } = normalizeBucket(bucket);
  return BUCKET_PRIORITY[normalized] || 0;
}

// Parse CSV line handling quoted fields
function parseCSVLine(line) {
  const result = [];
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

// Parse importance_standardised JSON
function parseImportanceStandardised(value) {
  if (!value || value === '-' || value === 'null') {
    return { skills: [] };
  }
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) {
      return { skills: [], error: 'Not an array' };
    }
    return {
      skills: parsed.map(item => ({
        skill: item.skill || '',
        bucket: item.bucket || '',
        thinking: item.thinking || '',
        mappingSimilarity: parseFloat(item.mapping_similarity) || 0,
      }))
    };
  } catch (e) {
    return { skills: [], error: e.message };
  }
}

// Escape XML
function escapeXml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

// Escape CSV
function escapeCsv(value) {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

// Main processing
async function processCSV() {
  console.log(`Processing: ${inputFile}`);
  console.log(`Output dir: ${outputDir}`);

  const nodes = new Map();
  const edges = [];
  const skillMap = new Map(); // For deduplication

  let headers = null;
  let rowCount = 0;
  let errorCount = 0;

  const fileStream = fs.createReadStream(inputFile, { encoding: 'utf8' });
  const rl = readline.createInterface({ input: fileStream, crlfDelay: Infinity });

  const startTime = Date.now();

  for await (const line of rl) {
    if (!headers) {
      headers = parseCSVLine(line);
      console.log(`Columns: ${headers.length}`);
      continue;
    }

    rowCount++;
    if (rowCount % 10000 === 0) {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      console.log(`Processed ${rowCount.toLocaleString()} rows... (${elapsed}s)`);
    }

    try {
      const values = parseCSVLine(line);
      const row = {};
      headers.forEach((h, i) => { row[h] = values[i] || ''; });

      // Get values
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
          ncoCode: ncoCode,
          groupName: groupName,
        });
      }

      // Job node
      const jobNodeId = `job:${jobId}`;
      if (!nodes.has(jobNodeId)) {
        nodes.set(jobNodeId, {
          id: jobNodeId,
          label: jobTitle,
          kind: 'job',
          ncoCode,
          groupName,
          jobId,
          jobTitle,
          companyName,
          postedAt,
          scheduleType,
          workFromHome: workFromHome === 'true' || workFromHome === 'TRUE',
          district,
          hybridNcoJd,
          tokenCount,
          highestSimilaritySpec,
          highestSimilarityScore,
          assignedOccupationGroup,
          salaryMean,
          salaryCurrency,
          salarySource,
        });

        // Category-Job edge
        edges.push({
          source: categoryId,
          target: jobNodeId,
          type: 'DIRECTED',
          rel: 'IN_CATEGORY',
        });
      }

      // Parse skills
      const { skills, error } = parseImportanceStandardised(importanceStd);
      if (error) errorCount++;

      for (const skillEntry of skills) {
        const skillId = `skill:${normalizeKey(skillEntry.skill)}`;
        const { normalized: normalizedBucket } = normalizeBucket(skillEntry.bucket);

        // Add skill node
        if (!nodes.has(skillId)) {
          nodes.set(skillId, {
            id: skillId,
            label: skillEntry.skill,
            kind: 'skill',
            skillNameOriginal: skillEntry.skill,
          });
        }

        // Deduplicate skill edges per job
        const edgeKey = `${jobNodeId}:${skillId}`;
        const existing = skillMap.get(edgeKey);

        if (!existing) {
          skillMap.set(edgeKey, {
            source: jobNodeId,
            target: skillId,
            type: 'DIRECTED',
            rel: 'REQUIRES_SKILL',
            bucket: normalizedBucket,
            mappingSimilarity: skillEntry.mappingSimilarity,
            thinking: skillEntry.thinking,
          });
        } else {
          // Keep higher priority bucket
          const existingPriority = getBucketPriority(existing.bucket);
          const newPriority = getBucketPriority(normalizedBucket);
          if (newPriority > existingPriority) {
            existing.bucket = normalizedBucket;
            existing.mappingSimilarity = Math.max(existing.mappingSimilarity, skillEntry.mappingSimilarity);
          }
        }
      }
    } catch (e) {
      errorCount++;
    }
  }

  // Add skill edges from map
  for (const edge of skillMap.values()) {
    edges.push(edge);
  }

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  console.log(`\nProcessing complete in ${elapsed}s`);
  console.log(`Rows: ${rowCount.toLocaleString()}`);
  console.log(`Nodes: ${nodes.size.toLocaleString()}`);
  console.log(`Edges: ${edges.length.toLocaleString()}`);
  console.log(`Errors: ${errorCount}`);

  // Count by type
  let categories = 0, jobs = 0, skills = 0;
  for (const node of nodes.values()) {
    if (node.kind === 'category') categories++;
    else if (node.kind === 'job') jobs++;
    else if (node.kind === 'skill') skills++;
  }
  console.log(`\nCategories: ${categories}, Jobs: ${jobs}, Skills: ${skills}`);

  // Write nodes.csv
  console.log('\nWriting nodes.csv...');
  const nodeColumns = ['id', 'label', 'kind', 'nco_code', 'group_name', 'job_id', 'job_title', 'company_name', 'posted_at', 'schedule_type', 'work_from_home', 'district', 'hybrid_nco_jd', 'token_count', 'highest_similarity_spec', 'highest_similarity_score_spec', 'assigned_occupation_group', 'salary_mean_inr_month', 'salary_currency_unit', 'salary_source', 'skill_name_original'];
  const nodesFile = fs.createWriteStream(path.join(outputDir, 'nodes.csv'));
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
  const edgeColumns = ['source', 'target', 'type', 'rel', 'bucket', 'bucket_raw', 'mapping_similarity', 'thinking'];
  const edgesFile = fs.createWriteStream(path.join(outputDir, 'edges.csv'));
  edgesFile.write(edgeColumns.join(',') + '\n');
  for (const edge of edges) {
    const row = [
      edge.source, edge.target, edge.type, edge.rel,
      edge.bucket || '', edge.bucketRaw || '',
      edge.mappingSimilarity || '', edge.thinking || ''
    ].map(escapeCsv);
    edgesFile.write(row.join(',') + '\n');
  }
  edgesFile.end();

  // Write GraphML
  console.log('Writing graph.graphml...');
  const graphmlFile = fs.createWriteStream(path.join(outputDir, 'graph.graphml'));
  graphmlFile.write(`<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="label" for="node" attr.name="label" attr.type="string"/>
  <key id="kind" for="node" attr.name="kind" attr.type="string"/>
  <key id="nco_code" for="node" attr.name="nco_code" attr.type="string"/>
  <key id="group_name" for="node" attr.name="group_name" attr.type="string"/>
  <key id="job_title" for="node" attr.name="job_title" attr.type="string"/>
  <key id="company_name" for="node" attr.name="company_name" attr.type="string"/>
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

  console.log('\nDone! Files written to:', outputDir);
  console.log('- nodes.csv');
  console.log('- edges.csv');
  console.log('- graph.graphml');
}

processCSV().catch(console.error);
