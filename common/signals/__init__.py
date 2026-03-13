"""Signal Aggregation Core — composite conviction scoring for trade entry/exit decisions."""

from common.signals.aggregator import CompositeSignal, SignalAggregator
from common.signals.asset_tuning import AssetClassConfig, get_config, get_session_adjustment
from common.signals.exit_manager import ExitAdvice, advise_exit, get_stop_multiplier
from common.signals.feedback import PerformanceFeedback, WeightAdjustment
from common.signals.performance_tracker import (
    AttributionRecord,
    PerformanceTracker,
    SourceAccuracy,
)
from common.signals.signal_cache import SignalCache

__all__ = [
    "AssetClassConfig",
    "AttributionRecord",
    "CompositeSignal",
    "ExitAdvice",
    "PerformanceFeedback",
    "PerformanceTracker",
    "SignalAggregator",
    "SignalCache",
    "SourceAccuracy",
    "WeightAdjustment",
    "advise_exit",
    "get_config",
    "get_session_adjustment",
    "get_stop_multiplier",
]
