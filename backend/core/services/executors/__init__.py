"""Task executor submodule — imports all executor functions and defines TASK_REGISTRY.

Each executor has signature: (params: dict, progress_cb: Callable) -> dict
except _sync_freqtrade_equity which takes no arguments.
"""

from core.services.executors.data import (
    _infer_asset_class,
    _run_data_quality,
    _run_data_refresh,
)
from core.services.executors.framework import (
    _run_hft_backtest,
    _run_nautilus_backtest,
    _run_vbt_screen,
)
from core.services.executors.market import (
    _run_coingecko_trending_refresh,
    _run_daily_report,
    _run_economic_calendar,
    _run_fear_greed_refresh,
    _run_funding_rate_refresh,
    _run_macro_data_refresh,
    _run_market_scan,
    _run_news_fetch,
    _run_reddit_sentiment_refresh,
    _run_sentiment_aggregation,
    _run_signal_feedback,
)
from core.services.executors.ml import (
    _run_adaptive_weighting,
    _run_conviction_audit,
    _run_ml_feedback,
    _run_ml_predict,
    _run_ml_retrain,
    _run_ml_training,
)
from core.services.executors.platform import (
    _run_autonomous_check,
    _run_db_backup,
    _run_db_maintenance,
    _run_pdf_report,
    _run_workflow,
)
from core.services.executors.regime import (
    _last_known_regimes,
    _run_regime_detection,
    _run_strategy_orchestration,
)
from core.services.executors.risk import (
    _run_daily_risk_reset,
    _run_risk_monitoring,
    _sync_freqtrade_equity,
)
from core.services.executors.trading import (
    _run_forex_paper_trading,
    _run_order_sync,
)
from core.services.executors._types import TaskExecutor

TASK_REGISTRY: dict[str, TaskExecutor] = {
    "data_refresh": _run_data_refresh,
    "regime_detection": _run_regime_detection,
    "order_sync": _run_order_sync,
    "data_quality": _run_data_quality,
    "news_fetch": _run_news_fetch,
    "workflow": _run_workflow,
    "risk_monitoring": _run_risk_monitoring,
    "db_maintenance": _run_db_maintenance,
    "vbt_screen": _run_vbt_screen,
    "ml_training": _run_ml_training,
    "market_scan": _run_market_scan,
    "daily_report": _run_daily_report,
    "forex_paper_trading": _run_forex_paper_trading,
    "nautilus_backtest": _run_nautilus_backtest,
    "hft_backtest": _run_hft_backtest,
    "ml_predict": _run_ml_predict,
    "ml_feedback": _run_ml_feedback,
    "ml_retrain": _run_ml_retrain,
    "conviction_audit": _run_conviction_audit,
    "strategy_orchestration": _run_strategy_orchestration,
    "signal_feedback": _run_signal_feedback,
    "adaptive_weighting": _run_adaptive_weighting,
    "economic_calendar": _run_economic_calendar,
    "funding_rate_refresh": _run_funding_rate_refresh,
    "fear_greed_refresh": _run_fear_greed_refresh,
    "reddit_sentiment_refresh": _run_reddit_sentiment_refresh,
    "coingecko_trending_refresh": _run_coingecko_trending_refresh,
    "macro_data_refresh": _run_macro_data_refresh,
    "daily_risk_reset": _run_daily_risk_reset,
    "autonomous_check": _run_autonomous_check,
    "pdf_report": _run_pdf_report,
    "db_backup": _run_db_backup,
}

__all__ = [
    "TASK_REGISTRY",
    "_infer_asset_class",
    "_last_known_regimes",
    "_run_adaptive_weighting",
    "_run_autonomous_check",
    "_run_coingecko_trending_refresh",
    "_run_conviction_audit",
    "_run_daily_report",
    "_run_daily_risk_reset",
    "_run_data_quality",
    "_run_data_refresh",
    "_run_db_backup",
    "_run_db_maintenance",
    "_run_economic_calendar",
    "_run_fear_greed_refresh",
    "_run_forex_paper_trading",
    "_run_funding_rate_refresh",
    "_run_hft_backtest",
    "_run_macro_data_refresh",
    "_run_market_scan",
    "_run_ml_feedback",
    "_run_ml_predict",
    "_run_ml_retrain",
    "_run_ml_training",
    "_run_nautilus_backtest",
    "_run_news_fetch",
    "_run_order_sync",
    "_run_pdf_report",
    "_run_reddit_sentiment_refresh",
    "_run_regime_detection",
    "_run_risk_monitoring",
    "_run_sentiment_aggregation",
    "_run_signal_feedback",
    "_run_strategy_orchestration",
    "_run_vbt_screen",
    "_run_workflow",
    "_sync_freqtrade_equity",
]
