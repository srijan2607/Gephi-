#!/usr/bin/env node

/**
 * Generate minimal GraphML from existing CSV files
 * Reduces file size by only including essential attributes
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const inputDir = process.argv[2] || './public/output';
const outputFile = path.join(inputDir, 'graph.graphml');

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

function escapeXml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

async function generateGraphML() {
  console.log('Generating minimal GraphML from CSV files...');
  console.log(`Input directory: ${inputDir}`);
  console.log(`Output file: ${outputFile}`);

  // Delete existing file
  if (fs.existsSync(outputFile)) {
    fs.unlinkSync(outputFile);
  }

  const graphml = fs.createWriteStream(outputFile);

  // Write header with rich attributes
  graphml.write(`<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="label" for="node" attr.name="label" attr.type="string"/>
  <key id="kind" for="node" attr.name="kind" attr.type="string"/>
  <key id="nco_code" for="node" attr.name="nco_code" attr.type="string"/>
  <key id="group_name" for="node" attr.name="group_name" attr.type="string"/>
  <key id="company" for="node" attr.name="company" attr.type="string"/>
  <key id="district" for="node" attr.name="district" attr.type="string"/>
  <key id="schedule" for="node" attr.name="schedule" attr.type="string"/>
  <key id="salary" for="node" attr.name="salary" attr.type="string"/>
  <key id="rel" for="edge" attr.name="rel" attr.type="string"/>
  <key id="bucket" for="edge" attr.name="bucket" attr.type="string"/>
  <key id="sim" for="edge" attr.name="mapping_similarity" attr.type="double"/>
  <graph id="G" edgedefault="directed">
`);

  // Read and write nodes
  console.log('Writing nodes...');
  const nodesFile = path.join(inputDir, 'nodes.csv');
  const nodesStream = fs.createReadStream(nodesFile, { encoding: 'utf8' });
  const nodesRL = readline.createInterface({ input: nodesStream, crlfDelay: Infinity });

  let headers = null;
  let nodeCount = 0;

  for await (const line of nodesRL) {
    if (!headers) {
      headers = parseCSVLine(line);
      continue;
    }

    const values = parseCSVLine(line);
    const row = {};
    headers.forEach((h, i) => { row[h] = values[i] || ''; });

    // Skip nodes with empty IDs
    if (!row.id || row.id.trim() === '') {
      continue;
    }

    // Write node with key attributes
    graphml.write(`    <node id="${escapeXml(row.id)}"><data key="label">${escapeXml(row.label)}</data><data key="kind">${escapeXml(row.kind)}</data><data key="nco_code">${escapeXml(row.nco_code || '')}</data><data key="group_name">${escapeXml(row.group_name || '')}</data></node>\n`);

    nodeCount++;
    if (nodeCount % 100000 === 0) {
      console.log(`  Wrote ${nodeCount.toLocaleString()} nodes...`);
    }
  }
  console.log(`  Total nodes: ${nodeCount.toLocaleString()}`);

  // Read and write edges
  console.log('Writing edges...');
  const edgesFile = path.join(inputDir, 'edges.csv');
  const edgesStream = fs.createReadStream(edgesFile, { encoding: 'utf8' });
  const edgesRL = readline.createInterface({ input: edgesStream, crlfDelay: Infinity });

  headers = null;
  let edgeCount = 0;

  for await (const line of edgesRL) {
    if (!headers) {
      headers = parseCSVLine(line);
      continue;
    }

    const values = parseCSVLine(line);
    const row = {};
    headers.forEach((h, i) => { row[h] = values[i] || ''; });

    // Skip edges with empty source or target
    if (!row.source || !row.target || row.source.trim() === '' || row.target.trim() === '') {
      continue;
    }

    // Write edge with key attributes
    graphml.write(`    <edge source="${escapeXml(row.source)}" target="${escapeXml(row.target)}"><data key="rel">${escapeXml(row.rel)}</data><data key="bucket">${escapeXml(row.bucket || '')}</data><data key="mapping_similarity">${row.mapping_similarity || 0}</data></edge>\n`);

    edgeCount++;
    if (edgeCount % 500000 === 0) {
      console.log(`  Wrote ${edgeCount.toLocaleString()} edges...`);
    }
  }
  console.log(`  Total edges: ${edgeCount.toLocaleString()}`);

  // Write footer
  graphml.write(`  </graph>
</graphml>
`);
  graphml.end();

  // Wait for file to finish writing
  await new Promise((resolve, reject) => {
    graphml.on('finish', resolve);
    graphml.on('error', reject);
  });

  const stats = fs.statSync(outputFile);
  const sizeMB = (stats.size / (1024 * 1024)).toFixed(1);
  const sizeGB = (stats.size / (1024 * 1024 * 1024)).toFixed(2);

  console.log(`\nDone! GraphML file: ${outputFile}`);
  console.log(`File size: ${sizeMB} MB (${sizeGB} GB)`);
}

generateGraphML().catch(console.error);
