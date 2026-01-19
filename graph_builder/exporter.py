"""
Export module for CSV and GraphML output.

Generates:
- nodes.csv: All nodes with attributes
- edges.csv: All edges with attributes
- graph.graphml: Gephi-ready GraphML
- skill_dictionary.csv: Skill normalization mapping
- bad_rows.csv: Failed rows with errors
"""

import os
import logging
from typing import Dict, List, Any, Optional

import pandas as pd

from .config import Config
from .graph import GraphBuilder
from .normalizer import SkillNormalizer
from .parser import DataParser
from .utils import escape_xml, format_bytes


logger = logging.getLogger('graph_builder')


class Exporter:
    """Export graph data to various formats."""

    def __init__(self, config: Config):
        self.config = config

    def export(
        self,
        graph: GraphBuilder,
        normalizer: SkillNormalizer,
        parser: DataParser
    ) -> Dict[str, str]:
        """
        Export all outputs.

        Args:
            graph: Built graph
            normalizer: Skill normalizer with dictionary
            parser: Parser with bad_rows

        Returns:
            Dict of output file paths
        """
        os.makedirs(self.config.output_dir, exist_ok=True)

        output_files = {}

        # Export based on requested formats
        if 'csv' in self.config.formats:
            output_files['nodes.csv'] = self._export_nodes_csv(graph)
            output_files['edges.csv'] = self._export_edges_csv(graph)

        if 'graphml' in self.config.formats:
            output_files['graph.graphml'] = self._export_graphml(graph)

        # Always export these
        output_files['skill_dictionary.csv'] = self._export_skill_dictionary(normalizer)
        output_files['bad_rows.csv'] = self._export_bad_rows(parser)

        # Log output summary
        logger.info("Export complete:")
        for name, path in output_files.items():
            if os.path.exists(path):
                size = os.path.getsize(path)
                logger.info(f"  {name}: {format_bytes(size)}")

        return output_files

    def _export_nodes_csv(self, graph: GraphBuilder) -> str:
        """Export nodes to CSV."""
        path = os.path.join(self.config.output_dir, 'nodes.csv')

        # Define column order
        columns = [
            'id', 'label', 'kind',
            # Job columns
            'job_title', 'company_name', 'posted_at', 'schedule_type',
            'work_from_home', 'district', 'nco_code', 'group_name',
            'assigned_occupation_group', 'salary_mean_inr_month',
            'salary_currency_unit', 'salary_source', 'skill_count',
            'token_count', 'highest_similarity_spec', 'highest_similarity_score',
            # Skill columns
            'canonical_key', 'aliases', 'job_count', 'max_similarity', 'avg_similarity',
            # Category columns (job_count reused)
        ]

        df = pd.DataFrame(list(graph.nodes.values()))

        # Reorder columns, keeping only those that exist
        existing_cols = [c for c in columns if c in df.columns]
        extra_cols = [c for c in df.columns if c not in columns]
        df = df[existing_cols + extra_cols]

        df.to_csv(path, index=False)
        logger.info(f"Exported {len(df):,} nodes to {path}")

        return path

    def _export_edges_csv(self, graph: GraphBuilder) -> str:
        """Export edges to CSV."""
        path = os.path.join(self.config.output_dir, 'edges.csv')

        # Define column order
        columns = ['source', 'target', 'rel', 'bucket', 'mapping_similarity', 'weight']

        if not self.config.drop_thinking:
            columns.append('thinking')

        df = pd.DataFrame(graph.edges)

        # Reorder columns
        existing_cols = [c for c in columns if c in df.columns]
        extra_cols = [c for c in df.columns if c not in columns]
        df = df[existing_cols + extra_cols]

        df.to_csv(path, index=False)
        logger.info(f"Exported {len(df):,} edges to {path}")

        return path

    def _export_graphml(self, graph: GraphBuilder) -> str:
        """Export graph to GraphML format."""
        path = os.path.join(self.config.output_dir, 'graph.graphml')

        # Delete existing file to prevent corruption
        if os.path.exists(path):
            os.remove(path)

        with open(path, 'w', encoding='utf-8') as f:
            # Write header
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write('<graphml xmlns="http://graphml.graphdrawing.org/xmlns">\n')

            # Write key definitions
            self._write_graphml_keys(f)

            # Start graph
            f.write('  <graph id="G" edgedefault="directed">\n')

            # Write nodes
            node_count = 0
            for node_id, node in graph.nodes.items():
                f.write(self._node_to_graphml(node))
                node_count += 1

                if node_count % 50000 == 0:
                    logger.debug(f"Written {node_count:,} nodes...")

            # Write edges
            edge_count = 0
            for edge in graph.edges:
                f.write(self._edge_to_graphml(edge))
                edge_count += 1

                if edge_count % 100000 == 0:
                    logger.debug(f"Written {edge_count:,} edges...")

            # Close graph
            f.write('  </graph>\n')
            f.write('</graphml>\n')

        logger.info(f"Exported GraphML to {path}")
        return path

    def _write_graphml_keys(self, f):
        """Write GraphML key definitions."""
        # Node attributes
        keys = [
            # Common
            ('label', 'node', 'string'),
            ('kind', 'node', 'string'),

            # Job-specific
            ('job_title', 'node', 'string'),
            ('company_name', 'node', 'string'),
            ('posted_at', 'node', 'string'),
            ('schedule_type', 'node', 'string'),
            ('work_from_home', 'node', 'string'),
            ('district', 'node', 'string'),
            ('nco_code', 'node', 'string'),
            ('group_name', 'node', 'string'),
            ('assigned_occupation_group', 'node', 'string'),
            ('salary_mean_inr_month', 'node', 'double'),
            ('salary_currency_unit', 'node', 'string'),
            ('salary_source', 'node', 'string'),
            ('skill_count', 'node', 'int'),
            ('token_count', 'node', 'int'),
            ('highest_similarity_score', 'node', 'double'),

            # Skill-specific
            ('canonical_key', 'node', 'string'),
            ('aliases', 'node', 'string'),
            ('job_count', 'node', 'int'),
            ('max_similarity', 'node', 'double'),
            ('avg_similarity', 'node', 'double'),

            # Edge attributes
            ('rel', 'edge', 'string'),
            ('bucket', 'edge', 'string'),
            ('mapping_similarity', 'edge', 'double'),
            ('weight', 'edge', 'double'),
        ]

        if not self.config.drop_thinking:
            keys.append(('thinking', 'edge', 'string'))

        for key_id, key_for, key_type in keys:
            f.write(
                f'  <key id="{key_id}" for="{key_for}" '
                f'attr.name="{key_id}" attr.type="{key_type}"/>\n'
            )

    def _node_to_graphml(self, node: Dict[str, Any]) -> str:
        """Convert a node to GraphML XML."""
        node_id = escape_xml(node['id'])
        xml = f'    <node id="{node_id}">\n'

        # Write data elements for each attribute
        for key, value in node.items():
            if key == 'id':
                continue
            if value is None or value == '':
                continue

            # Format value based on type
            if isinstance(value, float):
                formatted = str(round(value, 4))
            elif isinstance(value, bool):
                formatted = 'true' if value else 'false'
            else:
                formatted = escape_xml(str(value))

            xml += f'      <data key="{key}">{formatted}</data>\n'

        xml += '    </node>\n'
        return xml

    def _edge_to_graphml(self, edge: Dict[str, Any]) -> str:
        """Convert an edge to GraphML XML."""
        source = escape_xml(edge['source'])
        target = escape_xml(edge['target'])

        xml = f'    <edge source="{source}" target="{target}">\n'

        # Write data elements
        for key, value in edge.items():
            if key in ('source', 'target'):
                continue
            if value is None or value == '':
                continue

            # Skip thinking if configured
            if key == 'thinking' and self.config.drop_thinking:
                continue

            # Format value
            if isinstance(value, float):
                formatted = str(round(value, 4))
            else:
                formatted = escape_xml(str(value))

            xml += f'      <data key="{key}">{formatted}</data>\n'

        xml += '    </edge>\n'
        return xml

    def _export_skill_dictionary(self, normalizer: SkillNormalizer) -> str:
        """Export skill dictionary."""
        path = os.path.join(self.config.output_dir, 'skill_dictionary.csv')

        df = normalizer.export_dictionary()
        df.to_csv(path, index=False)

        logger.info(f"Exported {len(df):,} skills to {path}")
        return path

    def _export_bad_rows(self, parser: DataParser) -> str:
        """Export bad rows."""
        path = os.path.join(self.config.output_dir, 'bad_rows.csv')

        df = parser.get_bad_rows_df()
        df.to_csv(path, index=False)

        logger.info(f"Exported {len(df):,} bad rows to {path}")
        return path
