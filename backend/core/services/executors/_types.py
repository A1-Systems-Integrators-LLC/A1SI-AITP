"""Shared type aliases for task executors."""

from collections.abc import Callable
from typing import Any

ProgressCallback = Callable[[float, str], None]
TaskExecutor = Callable[[dict, ProgressCallback], dict[str, Any]]
