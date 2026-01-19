#!/usr/bin/env node

/**
 * Generate a sampled GraphML from existing CSV files
 * Creates a smaller graph for visualization in Gephi
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const inputDir = process.argv[2] || './public/output';
const sampleSize = parseInt(process.argv[3]) || 50000;
const outputFile = path.join(inputDir, 'graph-sample.graphml');

function escapeXml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

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

async function generateSampleGraphML() {
  console.log(`Generating sample GraphML (target: ~${sampleSize.toLocaleString()} nodes)...`);
  console.log(`Input directory: ${inputDir}`);
  console.log(`Output file: ${outputFile}`);

  // Step 1: Read all nodes and sample them
  console.log('\nStep 1: Reading and sampling nodes...');
  const nodesFile = path.join(inputDir, 'nodes.csv');
  const nodesStream = fs.createReadStream(nodesFile, { encoding: 'utf8' });
  const nodesRL = readline.createInterface({ input: nodesStream, crlfDelay: Infinity });

  let headers = null;
  const allNodes = [];

  for await (const line of nodesRL) {
    if (!headers) {
      headers = parseCSVLine(line);
      continue;
    }
    const values = parseCSVLine(line);
    const row = {};
    headers.forEach((h, i) => { row[h] = values[i] || ''; });

    if (row.id && row.id.trim() !== '') {
      allNodes.push(row);
    }
  }

  console.log(`  Total nodes in file: ${allNodes.length.toLocaleString()}`);

  // Sample nodes - prioritize categories, then sample jobs and skills
  const categories = allNodes.filter(n => n.kind === 'category');
  const jobs = allNodes.filter(n => n.kind === 'job');
  const skills = allNodes.filter(n => n.kind === 'skill');

  console.log(`  Categories: ${categories.length}, Jobs: ${jobs.length}, Skills: ${skills.length}`);

  // Take all categories, sample jobs and skills
  const sampledNodes = new Map();

  // Add all categories
  categories.forEach(n => sampledNodes.set(n.id, n));

  // Calculate how many jobs and skills to sample
  const remainingSlots = sampleSize - categories.length;
  const jobRatio = jobs.length / (jobs.length + skills.length);
  const jobSampleSize = Math.min(jobs.length, Math.floor(remainingSlots * jobRatio));
  const skillSampleSize = Math.min(skills.length, remainingSlots - jobSampleSize);

  // Random sample jobs
  const shuffledJobs = jobs.sort(() => Math.random() - 0.5);
  shuffledJobs.slice(0, jobSampleSize).forEach(n => sampledNodes.set(n.id, n));

  // Random sample skills
  const shuffledSkills = skills.sort(() => Math.random() - 0.5);
  shuffledSkills.slice(0, skillSampleSize).forEach(n => sampledNodes.set(n.id, n));

  console.log(`  Sampled nodes: ${sampledNodes.size.toLocaleString()}`);

  // Step 2: Read edges and keep only those connecting sampled nodes
  console.log('\nStep 2: Filtering edges...');
  const edgesFile = path.join(inputDir, 'edges.csv');
  const edgesStream = fs.createReadStream(edgesFile, { encoding: 'utf8' });
  const edgesRL = readline.createInterface({ input: edgesStream, crlfDelay: Infinity });

  headers = null;
  const sampledEdges = [];
  let totalEdges = 0;

  for await (const line of edgesRL) {
    if (!headers) {
      headers = parseCSVLine(line);
      continue;
    }

    totalEdges++;
    if (totalEdges % 1000000 === 0) {
      console.log(`  Processed ${totalEdges.toLocaleString()} edges...`);
    }

    const values = parseCSVLine(line);
    const row = {};
    headers.forEach((h, i) => { row[h] = values[i] || ''; });

    // Only include edge if both source and target are in sampled nodes
    if (row.source && row.target &&
        sampledNodes.has(row.source) && sampledNodes.has(row.target)) {
      sampledEdges.push(row);
    }
  }

  console.log(`  Total edges processed: ${totalEdges.toLocaleString()}`);
  console.log(`  Sampled edges: ${sampledEdges.length.toLocaleString()}`);

  // Step 3: Write GraphML
  console.log('\nStep 3: Writing GraphML...');

  if (fs.existsSync(outputFile)) {
    fs.unlinkSync(outputFile);
  }

  const graphml = fs.createWriteStream(outputFile);

  graphml.write(`<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="label" for="node" attr.name="label" attr.type="string"/>
  <key id="kind" for="node" attr.name="kind" attr.type="string"/>
  <key id="nco_code" for="node" attr.name="nco_code" attr.type="string"/>
  <key id="group_name" for="node" attr.name="group_name" attr.type="string"/>
  <key id="rel" for="edge" attr.name="rel" attr.type="string"/>
  <key id="bucket" for="edge" attr.name="bucket" attr.type="string"/>
  <key id="sim" for="edge" attr.name="mapping_similarity" attr.type="double"/>
  <graph id="G" edgedefault="directed">
`);

  // Write nodes
  let nodeCount = 0;
  for (const [id, node] of sampledNodes) {
    graphml.write(`    <node id="${escapeXml(id)}"><data key="label">${escapeXml(node.label)}</data><data key="kind">${escapeXml(node.kind)}</data><data key="nco_code">${escapeXml(node.nco_code || '')}</data><data key="group_name">${escapeXml(node.group_name || '')}</data></node>\n`);
    nodeCount++;
  }
  console.log(`  Wrote ${nodeCount.toLocaleString()} nodes`);

  // Write edges
  let edgeCount = 0;
  for (const edge of sampledEdges) {
    graphml.write(`    <edge source="${escapeXml(edge.source)}" target="${escapeXml(edge.target)}"><data key="rel">${escapeXml(edge.rel)}</data><data key="bucket">${escapeXml(edge.bucket || '')}</data><data key="sim">${edge.mapping_similarity || 0}</data></edge>\n`);
    edgeCount++;
  }
  console.log(`  Wrote ${edgeCount.toLocaleString()} edges`);

  graphml.write(`  </graph>
</graphml>
`);
  graphml.end();

  await new Promise((resolve, reject) => {
    graphml.on('finish', resolve);
    graphml.on('error', reject);
  });

  const stats = fs.statSync(outputFile);
  const sizeMB = (stats.size / (1024 * 1024)).toFixed(1);

  console.log(`\nDone! Sample GraphML: ${outputFile}`);
  console.log(`File size: ${sizeMB} MB`);
  console.log(`Nodes: ${nodeCount.toLocaleString()}, Edges: ${edgeCount.toLocaleString()}`);
}

generateSampleGraphML().catch(console.error);
