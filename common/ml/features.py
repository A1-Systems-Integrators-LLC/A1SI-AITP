"""ML Feature Engineering
======================
Transforms OHLCV DataFrames into feature matrices for ML models.
Uses shared indicators from common.indicators.technical.
"""

import logging

import numpy as np
import pandas as pd

from common.indicators.technical import (
    adx,
    atr_indicator,
    bollinger_bands,
    cci,
    ema,
    macd,
    mfi,
    obv,
    rsi,
    sma,
    stochastic,
    williams_r,
)

logger = logging.getLogger(__name__)

# Default feature config — can be overridden via platform_config.yaml
DEFAULT_FEATURE_CONFIG = {
    "lag_periods": [1, 2, 3, 5],
    "return_periods": [1, 3, 5, 10],
    "target_horizon": 3,  # bars ahead for binary target (multi-bar smooths noise)
    "target_dead_zone": 0.005,  # 0.5% dead zone — ambiguous returns dropped
    "max_features": 35,  # cap feature count to reduce overfitting on small datasets
    "drop_na": True,
}


def compute_indicator_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute indicator-based features from an OHLCV DataFrame.

    Args:
        df: DataFrame with columns [open, high, low, close, volume].

    Returns:
        DataFrame with indicator columns added (NaN rows from warmup preserved).

    """
    feat = pd.DataFrame(index=df.index)

    # --- Trend ---
    for p in [7, 14, 21, 50]:
        feat[f"sma_{p}"] = sma(df["close"], p)
        feat[f"ema_{p}"] = ema(df["close"], p)

    # Price relative to moving averages (normalized)
    for p in [21, 50]:
        feat[f"close_over_sma_{p}"] = df["close"] / feat[f"sma_{p}"] - 1
        feat[f"close_over_ema_{p}"] = df["close"] / feat[f"ema_{p}"] - 1

    # EMA crossover signals
    feat["ema_7_over_21"] = feat["ema_7"] / feat["ema_21"] - 1
    feat["ema_21_over_50"] = feat["ema_21"] / feat["ema_50"] - 1

    raw_ma_cols = [f"sma_{p}" for p in [7, 14, 21, 50]] + [f"ema_{p}" for p in [7, 14, 21, 50]]
    feat = feat.drop(columns=[c for c in raw_ma_cols if c in feat.columns])

    # --- Momentum ---
    feat["rsi_14"] = rsi(df["close"], 14)
    macd_df = macd(df["close"])
    feat["macd"] = macd_df["macd"]
    feat["macd_signal"] = macd_df["macd_signal"]
    feat["macd_hist"] = macd_df["macd_hist"]
    stoch_df = stochastic(df)
    feat["stoch_k"] = stoch_df["stoch_k"]
    feat["stoch_d"] = stoch_df["stoch_d"]
    feat["cci_20"] = cci(df)
    feat["williams_r_14"] = williams_r(df)
    feat["adx_14"] = adx(df, 14)

    # --- Volatility ---
    feat["atr_14"] = atr_indicator(df, 14)
    feat["atr_pct"] = feat["atr_14"] / df["close"]  # Normalized ATR
    bb_df = bollinger_bands(df["close"])
    feat["bb_width"] = bb_df["bb_width"]
    feat["bb_pct"] = bb_df["bb_pct"]

    # --- Volume ---
    feat["obv"] = obv(df)
    feat["mfi_14"] = mfi(df)
    feat["volume_sma_20"] = sma(df["volume"], 20)
    feat["volume_ratio"] = df["volume"] / feat["volume_sma_20"].replace(0, np.nan)

    return feat


def add_lag_features(feat: pd.DataFrame, lag_periods: list[int] | None = None) -> pd.DataFrame:
    """Add lagged values for key indicators.

    Args:
        feat: DataFrame of indicator features.
        lag_periods: List of lag periods (default: [1, 2, 3, 5]).

    Returns:
        DataFrame with lag columns appended.

    """
    if lag_periods is None:
        lag_periods = DEFAULT_FEATURE_CONFIG["lag_periods"]

    lag_cols = ["rsi_14", "macd_hist", "bb_pct", "volume_ratio", "adx_14"]
    existing = [c for c in lag_cols if c in feat.columns]

    result = feat.copy()
    for col in existing:
        for lag in lag_periods:
            result[f"{col}_lag{lag}"] = feat[col].shift(lag)

    return result


def add_return_features(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    """Compute multi-horizon returns as features.

    Args:
        df: Original OHLCV DataFrame.
        periods: Return lookback periods (default: [1, 3, 5, 10]).

    Returns:
        DataFrame with return columns.

    """
    if periods is None:
        periods = DEFAULT_FEATURE_CONFIG["return_periods"]

    result = pd.DataFrame(index=df.index)
    for p in periods:
        result[f"return_{p}"] = df["close"].pct_change(p)

    # High-low range as fraction of close
    result["hl_range_pct"] = (df["high"] - df["low"]) / df["close"]

    return result


def compute_target(
    df: pd.DataFrame,
    horizon: int = 1,
    dead_zone: float = 0.0,
) -> pd.Series:
    """Binary classification target with optional dead zone.

    Args:
        df: OHLCV DataFrame.
        horizon: Number of bars ahead for target (e.g. 3 = average of next 3 bars).
        dead_zone: Minimum absolute return to assign a label. Returns within
            [-dead_zone, +dead_zone] are set to NaN (dropped during training).
            Use 0.005 (0.5%) for crypto, 0.003 for equity/forex.

    Returns:
        Series of 0/1/NaN values. Last `horizon` rows will be NaN.

    """
    future_return = df["close"].shift(-horizon) / df["close"] - 1
    target = (future_return > 0).astype(float).where(future_return.notna())

    # Apply dead zone: ambiguous returns get NaN (dropped by dropna)
    if dead_zone > 0:
        ambiguous = future_return.abs() < dead_zone
        target = target.where(~ambiguous)

    return target


def add_regime_features(
    df: pd.DataFrame,
    regime_ordinal: int | None = None,
    regime_confidence: float | None = None,
    regime_adx: float | None = None,
) -> pd.DataFrame:
    """Add regime-related features.

    Args:
        df: OHLCV DataFrame.
        regime_ordinal: Current regime as ordinal (0-6). None fills with -1.
        regime_confidence: Regime detection confidence (0-1). None fills with 0.
        regime_adx: ADX value from regime detector. None fills with 0.

    Returns:
        DataFrame with regime feature columns.

    """
    feat = pd.DataFrame(index=df.index)
    feat["regime_ordinal"] = regime_ordinal if regime_ordinal is not None else -1
    feat["regime_confidence"] = regime_confidence if regime_confidence is not None else 0.0
    feat["regime_adx"] = regime_adx if regime_adx is not None else 0.0

    # Trend alignment: close above/below short-term EMA as a proxy
    ema_21 = ema(df["close"], 21)
    feat["regime_trend_alignment"] = (df["close"] / ema_21 - 1).clip(-0.1, 0.1) * 10

    return feat


def add_sentiment_features(
    sentiment_score: float | None = None,
    sentiment_conviction: float | None = None,
    sentiment_position_modifier: float | None = None,
    n_rows: int = 1,
) -> pd.DataFrame:
    """Add sentiment-derived features.

    Args:
        sentiment_score: Sentiment score (-1 to 1). None fills with 0.
        sentiment_conviction: Conviction level (0-1). None fills with 0.
        sentiment_position_modifier: Position modifier (0.8-1.2). None fills with 1.
        n_rows: Number of rows to generate.

    Returns:
        DataFrame with sentiment feature columns.

    """
    feat = pd.DataFrame(index=range(n_rows))
    feat["sentiment_score"] = sentiment_score if sentiment_score is not None else 0.0
    feat["sentiment_conviction"] = sentiment_conviction if sentiment_conviction is not None else 0.0
    feat["sentiment_position_modifier"] = (
        sentiment_position_modifier if sentiment_position_modifier is not None else 1.0
    )
    return feat


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add cyclical temporal features (hour, day-of-week, month).

    Uses sin/cos encoding to preserve cyclical nature.

    Args:
        df: DataFrame with a DatetimeIndex or numeric index.

    Returns:
        DataFrame with temporal feature columns.

    """
    feat = pd.DataFrame(index=df.index)

    if isinstance(df.index, pd.DatetimeIndex):
        hours = df.index.hour
        dows = df.index.dayofweek
        months = df.index.month
    else:
        # Fallback: fill with zeros (e.g., for non-datetime indices)
        n = len(df)
        hours = np.zeros(n)
        dows = np.zeros(n)
        months = np.ones(n)

    feat["hour_sin"] = np.sin(2 * np.pi * hours / 24)
    feat["hour_cos"] = np.cos(2 * np.pi * hours / 24)
    feat["dow_sin"] = np.sin(2 * np.pi * dows / 7)
    feat["dow_cos"] = np.cos(2 * np.pi * dows / 7)
    feat["month_sin"] = np.sin(2 * np.pi * (months - 1) / 12)
    feat["month_cos"] = np.cos(2 * np.pi * (months - 1) / 12)

    return feat


def add_volatility_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add volatility regime features.

    Args:
        df: OHLCV DataFrame.

    Returns:
        DataFrame with volatility regime feature columns.

    """
    feat = pd.DataFrame(index=df.index)

    # BB width percentile over 100 bars
    bb_df = bollinger_bands(df["close"])
    bb_w = bb_df["bb_width"]
    feat["bb_width_percentile_100"] = bb_w.rolling(100, min_periods=20).apply(
        lambda x: (x.values[-1] - x.min()) / (x.max() - x.min()) if x.max() > x.min() else 0.5,
        raw=False,
    )

    # ATR percentile over 100 bars
    atr_val = atr_indicator(df, 14)
    feat["atr_percentile_100"] = atr_val.rolling(100, min_periods=20).apply(
        lambda x: (x.values[-1] - x.min()) / (x.max() - x.min()) if x.max() > x.min() else 0.5,
        raw=False,
    )

    # Realized volatility (20-bar)
    log_returns = np.log(df["close"] / df["close"].shift(1))
    feat["realized_vol_20"] = log_returns.rolling(20, min_periods=5).std() * np.sqrt(252)

    # Volatility of volatility (vol-of-vol, 20-bar)
    feat["vol_of_vol_20"] = feat["realized_vol_20"].rolling(20, min_periods=5).std()

    return feat


def add_cross_asset_features(
    df: pd.DataFrame,
    reference_df: pd.DataFrame | None = None,
    asset_class: str = "crypto",
    window: int = 20,
) -> pd.DataFrame:
    """Add cross-asset correlation and lead-lag features.

    Uses a reference asset to compute:
    - Rolling correlation (20-bar)
    - Lead-lag returns (reference leads by 1-4 bars)
    - Relative strength (asset return / reference return)

    Reference assets by class:
    - crypto: BTC/USDT (for alt coins)
    - equity: SPY (S&P 500 proxy)
    - forex: DXY proxy (via USD index)

    Args:
        df: OHLCV DataFrame for the target asset.
        reference_df: OHLCV DataFrame for reference asset. None = skip.
        asset_class: Used only for labeling.
        window: Rolling window for correlation.

    Returns:
        DataFrame with cross-asset feature columns.
    """
    feat = pd.DataFrame(index=df.index)

    if reference_df is None or reference_df.empty:
        # No reference data available — fill with neutral values
        feat["cross_corr"] = 0.0
        feat["cross_lead1_return"] = 0.0
        feat["cross_lead2_return"] = 0.0
        feat["relative_strength"] = 0.0
        return feat

    # Align reference to target index via forward-fill
    ref_close = reference_df["close"].reindex(df.index, method="ffill")

    # Target and reference returns
    target_ret = df["close"].pct_change()
    ref_ret = ref_close.pct_change()

    # Rolling correlation
    feat["cross_corr"] = target_ret.rolling(window, min_periods=5).corr(ref_ret)

    # Lead-lag: reference returns from 1 and 2 bars ago
    # (reference leads → shifted reference returns predict current moves)
    feat["cross_lead1_return"] = ref_ret.shift(1)
    feat["cross_lead2_return"] = ref_ret.shift(2)

    # Relative strength: cumulative ratio over window
    cum_target = target_ret.rolling(window, min_periods=5).sum()
    cum_ref = ref_ret.rolling(window, min_periods=5).sum()
    feat["relative_strength"] = cum_target - cum_ref

    return feat


def build_feature_matrix(
    df: pd.DataFrame,
    config: dict | None = None,
    regime_ordinal: int | None = None,
    regime_confidence: float | None = None,
    regime_adx: float | None = None,
    sentiment_score: float | None = None,
    sentiment_conviction: float | None = None,
    sentiment_position_modifier: float | None = None,
    include_temporal: bool = False,
    include_volatility_regime: bool = False,
    include_regime: bool = False,
    include_sentiment: bool = False,
    include_cross_asset: bool = False,
    reference_df: pd.DataFrame | None = None,
    asset_class: str = "crypto",
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Full pipeline: OHLCV → feature matrix + target.

    Args:
        df: OHLCV DataFrame with columns [open, high, low, close, volume].
        config: Optional override for DEFAULT_FEATURE_CONFIG.
        regime_ordinal: Current regime as ordinal (0-6) for regime features.
        regime_confidence: Regime detection confidence for regime features.
        regime_adx: ADX from regime detector for regime features.
        sentiment_score: Sentiment score for sentiment features.
        sentiment_conviction: Sentiment conviction for sentiment features.
        sentiment_position_modifier: Position modifier for sentiment features.
        include_temporal: Whether to include cyclical temporal features.
        include_volatility_regime: Whether to include volatility regime features.
        include_regime: Whether to include regime features.
        include_sentiment: Whether to include sentiment features.

    Returns:
        Tuple of (X features, y target, feature_names).
        Rows with any NaN are dropped.

    """
    cfg = {**DEFAULT_FEATURE_CONFIG, **(config or {})}

    # Compute all features
    indicators = compute_indicator_features(df)
    returns = add_return_features(df, cfg["return_periods"])
    parts = [indicators, returns]

    if include_regime:
        regime_feat = add_regime_features(df, regime_ordinal, regime_confidence, regime_adx)
        parts.append(regime_feat)

    if include_sentiment:
        sent_feat = add_sentiment_features(
            sentiment_score,
            sentiment_conviction,
            sentiment_position_modifier,
            n_rows=len(df),
        )
        sent_feat.index = df.index
        parts.append(sent_feat)

    if include_temporal:
        temp_feat = add_temporal_features(df)
        parts.append(temp_feat)

    if include_volatility_regime:
        vol_feat = add_volatility_regime_features(df)
        parts.append(vol_feat)

    if include_cross_asset:
        cross_feat = add_cross_asset_features(df, reference_df, asset_class)
        parts.append(cross_feat)

    # Funding rate features (crypto only, optional)
    if cfg.get("include_funding_rate", False):
        try:
            from common.data_pipeline.pipeline import load_funding_rates

            symbol = cfg.get("symbol", "")
            fr_df = load_funding_rates(symbol) if symbol else pd.DataFrame()
            if not fr_df.empty and "funding_rate" in fr_df.columns:
                # Align funding rates to OHLCV index via forward-fill
                fr_aligned = fr_df["funding_rate"].reindex(df.index, method="ffill")
                funding_feat = pd.DataFrame(index=df.index)
                funding_feat["funding_rate"] = fr_aligned
                funding_feat["funding_rate_ma8"] = fr_aligned.rolling(8).mean()
                funding_feat["funding_rate_positive"] = (fr_aligned > 0).astype(float)
                parts.append(funding_feat)
        except Exception:
            pass  # Funding rates optional — silently skip

    features = pd.concat(parts, axis=1)
    features = add_lag_features(features, cfg["lag_periods"])

    # Target
    target = compute_target(df, cfg["target_horizon"], cfg.get("target_dead_zone", 0.0))

    # Combine and drop NaN
    combined = features.copy()
    combined["__target__"] = target

    if cfg["drop_na"]:
        combined = combined.dropna()

    y = combined.pop("__target__")
    x_feat = combined

    # Feature reduction: drop highly correlated features (>0.95)
    max_features = cfg.get("max_features", 0)
    if max_features > 0 and len(x_feat.columns) > max_features:
        x_feat = _reduce_features(x_feat, max_features)

    feature_names = list(x_feat.columns)

    logger.info("Feature matrix: %d rows x %d features", len(x_feat), len(feature_names))
    return x_feat, y, feature_names


def _reduce_features(
    x_feat: pd.DataFrame,
    max_features: int = 35,
    corr_threshold: float = 0.95,
) -> pd.DataFrame:
    """Reduce features by removing highly correlated columns.

    1. Drop columns with >corr_threshold Pearson correlation (keep first).
    2. If still over max_features, drop lowest-variance columns.
    """
    # Step 1: Correlation filter
    corr = x_feat.corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    to_drop = [col for col in upper.columns if any(upper[col] > corr_threshold)]
    if to_drop:
        logger.info(
            "Dropping %d correlated features (>%.2f): %s", len(to_drop), corr_threshold, to_drop[:5]
        )
        x_feat = x_feat.drop(columns=to_drop)

    # Step 2: Variance filter if still over budget
    if len(x_feat.columns) > max_features:
        variances = x_feat.var().sort_values(ascending=False)
        keep = variances.index[:max_features].tolist()
        dropped = len(x_feat.columns) - max_features
        logger.info("Dropping %d low-variance features to reach %d", dropped, max_features)
        x_feat = x_feat[keep]

    return x_feat
