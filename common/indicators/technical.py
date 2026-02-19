"""
Crypto-Investor Shared Technical Indicators
=============================================
Indicator library used across all framework tiers.
These are pure-pandas implementations that work with any OHLCV DataFrame.
"""

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────
# Trend Indicators
# ──────────────────────────────────────────────

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1, dtype=float)
    return series.rolling(window=period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def hull_ma(series: pd.Series, period: int) -> pd.Series:
    half_wma = wma(series, period // 2) * 2
    full_wma = wma(series, period)
    diff = half_wma - full_wma
    return wma(diff, int(np.sqrt(period)))


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """ATR-based Supertrend indicator."""
    hl2 = (df["high"] + df["low"]) / 2
    atr = atr_indicator(df, period)

    upper = hl2 + (multiplier * atr)
    lower = hl2 - (multiplier * atr)

    st = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)

    st.iloc[0] = upper.iloc[0]
    direction.iloc[0] = -1

    for i in range(1, len(df)):
        if df["close"].iloc[i] > upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["close"].iloc[i] < lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        if direction.iloc[i] == 1:
            st.iloc[i] = max(lower.iloc[i], st.iloc[i - 1]) if direction.iloc[i - 1] == 1 else lower.iloc[i]
        else:
            st.iloc[i] = min(upper.iloc[i], st.iloc[i - 1]) if direction.iloc[i - 1] == -1 else upper.iloc[i]

    result = df[[]].copy()
    result["supertrend"] = st
    result["supertrend_direction"] = direction
    return result


# ──────────────────────────────────────────────
# Momentum Indicators
# ──────────────────────────────────────────────

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "macd_signal": signal_line, "macd_hist": histogram})


def stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
    low_min = df["low"].rolling(window=k_period).min()
    high_max = df["high"].rolling(window=k_period).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min)
    d = k.rolling(window=d_period).mean()
    return pd.DataFrame({"stoch_k": k, "stoch_d": d})


def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(window=period).mean()
    mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma_tp) / (0.015 * mad)


def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_max = df["high"].rolling(window=period).max()
    low_min = df["low"].rolling(window=period).min()
    return -100 * (high_max - df["close"]) / (high_max - low_min)


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength (0-100)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr_val = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_val
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean() / atr_val
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


# ──────────────────────────────────────────────
# Volatility Indicators
# ──────────────────────────────────────────────

def atr_indicator(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()


def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    mid = sma(series, period)
    std = series.rolling(window=period).std()
    return pd.DataFrame({
        "bb_upper": mid + (std * std_dev),
        "bb_mid": mid,
        "bb_lower": mid - (std * std_dev),
        "bb_width": ((mid + std * std_dev) - (mid - std * std_dev)) / mid,
        "bb_pct": (series - (mid - std * std_dev)) / ((mid + std * std_dev) - (mid - std * std_dev)),
    })


def keltner_channels(df: pd.DataFrame, ema_period: int = 20, atr_period: int = 10, multiplier: float = 2.0) -> pd.DataFrame:
    mid = ema(df["close"], ema_period)
    atr_val = atr_indicator(df, atr_period)
    return pd.DataFrame({
        "kc_upper": mid + (atr_val * multiplier),
        "kc_mid": mid,
        "kc_lower": mid - (atr_val * multiplier),
    })


# ──────────────────────────────────────────────
# Volume Indicators
# ──────────────────────────────────────────────

def obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume."""
    direction = np.where(df["close"] > df["close"].shift(), 1,
                         np.where(df["close"] < df["close"].shift(), -1, 0))
    return (df["volume"] * direction).cumsum()


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume Weighted Average Price (intraday, resets each day)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (tp * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    return cum_tp_vol / cum_vol


def mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Money Flow Index."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]
    pos_mf = mf.where(tp > tp.shift(), 0).rolling(window=period).sum()
    neg_mf = mf.where(tp < tp.shift(), 0).rolling(window=period).sum()
    mf_ratio = pos_mf / neg_mf.replace(0, np.nan)
    return 100 - (100 / (1 + mf_ratio))


# ──────────────────────────────────────────────
# Composite: Add all indicators to DataFrame
# ──────────────────────────────────────────────

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add a comprehensive set of indicators to an OHLCV DataFrame."""
    result = df.copy()

    # Trend
    for p in [7, 14, 21, 50, 100, 200]:
        result[f"sma_{p}"] = sma(result["close"], p)
        result[f"ema_{p}"] = ema(result["close"], p)

    result["hull_ma_9"] = hull_ma(result["close"], 9)

    # Momentum
    result["rsi_14"] = rsi(result["close"], 14)
    macd_df = macd(result["close"])
    result = pd.concat([result, macd_df], axis=1)
    stoch_df = stochastic(result)
    result = pd.concat([result, stoch_df], axis=1)
    result["cci_20"] = cci(result)
    result["williams_r_14"] = williams_r(result)

    # Volatility
    result["atr_14"] = atr_indicator(result, 14)
    bb_df = bollinger_bands(result["close"])
    result = pd.concat([result, bb_df], axis=1)

    # Volume
    result["obv"] = obv(result)
    result["mfi_14"] = mfi(result)
    result["volume_sma_20"] = sma(result["volume"], 20)
    result["volume_ratio"] = result["volume"] / result["volume_sma_20"]

    # Price action
    result["returns"] = result["close"].pct_change()
    result["log_returns"] = np.log(result["close"] / result["close"].shift(1))

    return result
