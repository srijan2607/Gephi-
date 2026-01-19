"""
Utility functions for the graph builder.
"""

import re
import logging
import unicodedata
from typing import Optional, Any
from datetime import datetime


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return a logger instance."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    return logging.getLogger('graph_builder')


def slugify(text: str) -> str:
    """
    Convert text to a URL-safe slug.

    Examples:
        slugify("Python Programming") -> "python-programming"
        slugify("Machine Learning & AI") -> "machine-learning-ai"
    """
    if not text:
        return ""

    # Convert to lowercase
    text = text.lower()

    # Normalize unicode characters
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')

    # Replace non-alphanumeric with hyphens
    text = re.sub(r'[^a-z0-9]+', '-', text)

    # Remove leading/trailing hyphens
    text = text.strip('-')

    # Collapse multiple hyphens
    text = re.sub(r'-+', '-', text)

    return text


def escape_xml(text: str) -> str:
    """
    Escape special characters for XML.

    Handles: & < > " '
    """
    if not text:
        return ""

    text = str(text)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')

    # Remove control characters that are invalid in XML
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    return text


def safe_float(val: Any, default: float = 0.0) -> float:
    """
    Safely parse a value to float.

    Returns default if parsing fails or value is None/NaN.
    """
    if val is None:
        return default

    try:
        import pandas as pd
        if pd.isna(val):
            return default
    except (ImportError, TypeError):
        pass

    try:
        result = float(val)
        # Check for NaN
        if result != result:  # NaN check
            return default
        return result
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: int = 0) -> int:
    """Safely parse a value to int."""
    if val is None:
        return default

    try:
        import pandas as pd
        if pd.isna(val):
            return default
    except (ImportError, TypeError):
        pass

    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def safe_str(val: Any, default: str = "") -> str:
    """Safely convert a value to string, handling None and NaN."""
    if val is None:
        return default

    try:
        import pandas as pd
        if pd.isna(val):
            return default
    except (ImportError, TypeError):
        pass

    return str(val).strip()


def parse_boolean(val: Any) -> Optional[bool]:
    """
    Parse a value to boolean.

    Returns:
        True for: 'yes', 'true', '1', 'y', True
        False for: 'no', 'false', '0', 'n', False
        None for: empty, None, other values
    """
    if val is None:
        return None

    try:
        import pandas as pd
        if pd.isna(val):
            return None
    except (ImportError, TypeError):
        pass

    if isinstance(val, bool):
        return val

    val_str = str(val).lower().strip()

    if val_str in ('yes', 'true', '1', 'y'):
        return True
    elif val_str in ('no', 'false', '0', 'n'):
        return False
    elif val_str == '':
        return None

    return None


def format_bytes(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


def z_score(confidence_level: float) -> float:
    """
    Get Z-score for a given confidence level.

    Common values:
        0.90 -> 1.645
        0.95 -> 1.960
        0.99 -> 2.576
    """
    z_scores = {
        0.90: 1.645,
        0.95: 1.960,
        0.99: 2.576,
        0.999: 3.291
    }

    if confidence_level in z_scores:
        return z_scores[confidence_level]

    # For other values, use scipy if available
    try:
        from scipy import stats
        return stats.norm.ppf(1 - (1 - confidence_level) / 2)
    except ImportError:
        # Fallback to 1.96 (95% CI)
        return 1.96


def truncate_string(s: str, max_length: int = 100) -> str:
    """Truncate a string to max_length, adding ellipsis if truncated."""
    if not s or len(s) <= max_length:
        return s
    return s[:max_length - 3] + "..."
