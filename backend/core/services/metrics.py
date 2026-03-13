"""Lightweight Prometheus-compatible metrics collector.
No external dependencies — memory-bounded, thread-safe.
"""

import threading
import time
from collections import defaultdict, deque


class MetricsCollector:
    """Singleton metrics collector producing Prometheus text format."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._gauges: dict[str, float] = {}
                    cls._instance._counters: dict[str, float] = defaultdict(float)
                    cls._instance._histograms: dict[str, deque] = defaultdict(
                        lambda: deque(maxlen=1000),
                    )
                    cls._instance._data_lock = threading.Lock()
        return cls._instance

    def gauge(self, name: str, value: float, labels: dict | None = None) -> None:
        key = self._key(name, labels)
        with self._data_lock:
            self._gauges[key] = value

    def counter_inc(self, name: str, labels: dict | None = None, amount: float = 1) -> None:
        key = self._key(name, labels)
        with self._data_lock:
            self._counters[key] += amount

    def histogram_observe(self, name: str, value: float, labels: dict | None = None) -> None:
        key = self._key(name, labels)
        with self._data_lock:
            self._histograms[key].append(value)

    # Metric type annotations for Prometheus
    _METRIC_TYPES: dict[str, tuple[str, str]] = {
        "portfolio_equity": ("gauge", "Current portfolio equity in USD"),
        "portfolio_drawdown": ("gauge", "Current drawdown from peak equity"),
        "risk_halt_active": ("gauge", "1 if risk halt is active, 0 otherwise"),
        "active_orders": ("gauge", "Number of active orders by mode"),
        "job_queue_pending": ("gauge", "Number of pending background jobs"),
        "job_queue_running": ("gauge", "Number of running background jobs"),
        "circuit_breaker_state": (
            "gauge",
            "Circuit breaker state (0=closed, 0.5=half_open, 1=open)",
        ),
        "scheduler_running": ("gauge", "1 if scheduler is running, 0 otherwise"),
        "ml_models_total": ("gauge", "Total number of ML models in registry"),
        "orchestrator_strategies_paused": ("gauge", "Number of strategies currently paused"),
        "signal_cache_size": ("gauge", "Number of cached signal computations"),
        "orders_created_total": ("counter", "Total orders created"),
    }

    def collect(self) -> str:
        """Produce Prometheus text exposition format with HELP/TYPE annotations."""
        lines = []
        seen_bases: set[str] = set()

        def _emit_annotation(key: str) -> None:
            # Extract base metric name (before { or label)
            base = key.split("{", maxsplit=1)[0] if "{" in key else key
            if base not in seen_bases:
                seen_bases.add(base)
                info = self._METRIC_TYPES.get(base)
                if info:
                    lines.append(f"# HELP {base} {info[1]}")
                    lines.append(f"# TYPE {base} {info[0]}")

        with self._data_lock:
            for key, value in sorted(self._gauges.items()):
                _emit_annotation(key)
                lines.append(f"{key} {value}")
            for key, value in sorted(self._counters.items()):
                _emit_annotation(key)
                lines.append(f"{key} {value}")
            for key, values in sorted(self._histograms.items()):
                if values:
                    base = key.split("{")[0] if "{" in key else key
                    if base not in seen_bases:
                        seen_bases.add(base)
                        lines.append(f"# TYPE {base} summary")
                    sorted_vals = sorted(values)
                    count = len(sorted_vals)
                    total = sum(sorted_vals)
                    lines.append(f"{key}_count {count}")
                    lines.append(f"{key}_sum {total:.6f}")
                    for q in (0.5, 0.9, 0.99):
                        idx = min(int(q * count), count - 1)
                        lines.append(f'{key}{{quantile="{q}"}} {sorted_vals[idx]:.6f}')
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _key(name: str, labels: dict | None = None) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


# Module-level singleton access
metrics = MetricsCollector()


def timed(metric_name: str, labels: dict | None = None):
    """Context manager to record duration as a histogram observation."""

    class Timer:
        def __enter__(self):
            self.start = time.monotonic()
            return self

        def __exit__(self, *args):
            duration = time.monotonic() - self.start
            metrics.histogram_observe(metric_name, duration, labels)

    return Timer()
