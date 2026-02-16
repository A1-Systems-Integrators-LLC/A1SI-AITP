"""
Platform bridge — resolves sys.path so backend can import common.*, research.*, nautilus.*.
"""

import sys
from pathlib import Path

# Project root: platform_bridge.py -> core -> backend -> crypto-investor
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def ensure_platform_imports() -> None:
    """Add project root to sys.path so platform modules are importable."""
    root_str = str(PROJECT_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def get_processed_dir() -> Path:
    """Return the shared Parquet data directory."""
    d = PROJECT_ROOT / "data" / "processed"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_research_results_dir() -> Path:
    """Return the research results directory."""
    d = PROJECT_ROOT / "research" / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_freqtrade_dir() -> Path:
    """Return the Freqtrade directory."""
    return PROJECT_ROOT / "freqtrade"


def get_platform_config_path() -> Path:
    """Return path to platform_config.yaml."""
    return PROJECT_ROOT / "configs" / "platform_config.yaml"
