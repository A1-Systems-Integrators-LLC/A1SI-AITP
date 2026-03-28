"""Registry mapping task_type strings to executor functions.

Each executor has signature: (params: dict, progress_cb: Callable) -> dict

Shared types (ProgressCallback, TaskExecutor) are defined in
core.services.executors._types to avoid circular imports.
All executor implementations live in core.services.executors submodules.
This module re-exports them so existing imports continue to work.
"""

import logging

from core.services.executors import (  # noqa: F401
    TASK_REGISTRY,
    _infer_asset_class,
    _last_known_regimes,
    _run_adaptive_weighting,
    _run_autonomous_check,
    _run_coingecko_trending_refresh,
    _run_conviction_audit,
    _run_daily_report,
    _run_daily_risk_reset,
    _run_data_quality,
    _run_data_refresh,
    _run_db_backup,
    _run_db_maintenance,
    _run_economic_calendar,
    _run_fear_greed_refresh,
    _run_forex_paper_trading,
    _run_funding_rate_refresh,
    _run_hft_backtest,
    _run_macro_data_refresh,
    _run_market_scan,
    _run_ml_feedback,
    _run_ml_predict,
    _run_ml_retrain,
    _run_ml_training,
    _run_nautilus_backtest,
    _run_news_fetch,
    _run_order_sync,
    _run_pdf_report,
    _run_reddit_sentiment_refresh,
    _run_regime_detection,
    _run_risk_monitoring,
    _run_sentiment_aggregation,
    _run_signal_feedback,
    _run_strategy_orchestration,
    _run_vbt_screen,
    _run_workflow,
    _sync_freqtrade_equity,
)
from core.services.executors._types import ProgressCallback, TaskExecutor  # noqa: F401

logger = logging.getLogger("scheduler")
