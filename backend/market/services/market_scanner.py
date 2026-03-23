"""MarketScannerService — scans watchlist for trading opportunities.

Detects volume surges, RSI bounces, breakout candidates, trend pullbacks,
and momentum shifts across all configured pairs. Stores results as
MarketOpportunity records and optionally broadcasts high-score alerts.
"""

import logging
import time
from datetime import timedelta
from typing import Any

import pandas as pd
from django.db import OperationalError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Per-asset-class detection thresholds
_THRESHOLDS: dict[str, dict[str, float]] = {
    "crypto": {
        "volume_surge_ratio": 2.0,
        "pullback_min_pct": 3.0,
        "pullback_max_pct": 5.0,
        "breakout_distance_pct": 2.0,
    },
    "forex": {
        "volume_surge_ratio": 1.5,
        "pullback_min_pct": 0.3,
        "pullback_max_pct": 1.0,
        "breakout_distance_pct": 0.5,
    },
    "equity": {
        "volume_surge_ratio": 2.0,
        "pullback_min_pct": 2.0,
        "pullback_max_pct": 5.0,
        "breakout_distance_pct": 2.0,
    },
}


class MarketScannerService:
    """Scan pairs for actionable setups across asset classes."""

    # Score thresholds
    HIGH_SCORE_WS_THRESHOLD = 75
    HIGH_SCORE_TELEGRAM_THRESHOLD = 80

    def scan_all(
        self,
        timeframe: str = "1h",
        asset_class: str = "crypto",
    ) -> dict[str, Any]:
        """Run all scans on the watchlist for the given asset class. Returns summary."""
        from core.platform_bridge import ensure_platform_imports, get_platform_config

        ensure_platform_imports()
        from common.data_pipeline.pipeline import load_ohlcv
        from common.indicators.technical import (
            adx,
            ema,
            macd,
            rsi,
            sma,
        )

        config = get_platform_config()
        watchlist_key = {
            "crypto": "watchlist",
            "equity": "equity_watchlist",
            "forex": "forex_watchlist",
        }.get(asset_class, "watchlist")
        symbols = config.get("data", {}).get(watchlist_key, [])

        if not symbols:
            return {"status": "skipped", "reason": f"No {asset_class} watchlist configured"}

        exchange_id = "yfinance" if asset_class in ("equity", "forex") else "kraken"
        thresholds = _THRESHOLDS.get(asset_class, _THRESHOLDS["crypto"])

        from market.models import MarketOpportunity

        now = timezone.now()
        expires_at = now + timedelta(hours=24)
        opportunities_created = 0
        symbols_scanned = 0
        errors = 0

        for symbol in symbols:
            try:
                df = load_ohlcv(symbol, timeframe, exchange_id=exchange_id)
                if df.empty or len(df) < 50:
                    continue

                symbols_scanned += 1

                # Pre-compute indicators
                close = df["close"]
                volume = df["volume"]
                rsi_val = rsi(close, 14)
                adx_val = adx(df, 14)
                ema_50 = ema(close, 50)
                sma_20 = sma(close, 20)
                macd_df = macd(close)

                latest_close = float(close.iloc[-1])
                latest_rsi = float(rsi_val.iloc[-1]) if not rsi_val.empty else 50.0
                latest_adx = float(adx_val.iloc[-1]) if not adx_val.empty else 0.0

                detections = []

                # --- Volume Surge ---
                opp = self._check_volume_surge(
                    symbol, volume, latest_close, timeframe,
                    surge_ratio=thresholds["volume_surge_ratio"],
                    is_tick_volume=(asset_class == "forex"),
                )
                if opp:
                    detections.append(opp)

                # --- RSI Bounce ---
                opp = self._check_rsi_bounce(symbol, rsi_val, latest_close, timeframe)
                if opp:
                    detections.append(opp)

                # --- Breakout Candidate ---
                opp = self._check_breakout(
                    symbol, close, volume, sma_20, latest_close, timeframe,
                    distance_pct=thresholds["breakout_distance_pct"],
                )
                if opp:
                    detections.append(opp)

                # --- Trend Pullback ---
                opp = self._check_trend_pullback(
                    symbol, close, adx_val, ema_50, latest_close, timeframe,
                    pullback_min=thresholds["pullback_min_pct"],
                    pullback_max=thresholds["pullback_max_pct"],
                )
                if opp:
                    detections.append(opp)

                # --- Momentum Shift ---
                opp = self._check_momentum_shift(
                    symbol, macd_df, latest_close, timeframe,
                )
                if opp:
                    detections.append(opp)

                # Save with deduplication
                for det in detections:
                    det = self._enrich_score(det, latest_rsi, latest_adx)
                    created = self._save_opportunity(
                        MarketOpportunity, symbol, det, asset_class,
                        timeframe, expires_at, now,
                    )
                    if created:
                        opportunities_created += 1
                    self._maybe_alert(symbol, det, asset_class)

            except OperationalError:
                logger.error("Scanner DB error for %s", symbol, exc_info=True)
                errors += 1
            except Exception:
                logger.warning("Scanner error for %s", symbol, exc_info=True)
                errors += 1

        # Expire old opportunities
        expired = MarketOpportunity.objects.filter(expires_at__lt=now).delete()[0]

        return {
            "status": "completed",
            "asset_class": asset_class,
            "symbols_scanned": symbols_scanned,
            "opportunities_created": opportunities_created,
            "expired_cleaned": expired,
            "errors": errors,
        }

    # ── Opportunity detectors ────────────────────────────────────

    @staticmethod
    def _check_volume_surge(
        symbol: str,
        volume: pd.Series,
        latest_close: float,
        timeframe: str,
        *,
        surge_ratio: float = 2.0,
        is_tick_volume: bool = False,
    ) -> dict[str, Any] | None:
        """24h volume > surge_ratio x 7-day average."""
        if len(volume) < 168:  # Need ~7 days of hourly data
            return None

        vol_24h = float(volume.iloc[-24:].sum())
        vol_7d_avg = float(volume.iloc[-168:].mean()) * 24
        if vol_7d_avg <= 0:
            return None

        ratio = vol_24h / vol_7d_avg
        if ratio < surge_ratio:
            return None

        score = min(int(40 + (ratio - surge_ratio) * 15), 90)
        details: dict[str, Any] = {
            "price": latest_close,
            "volume_24h": round(vol_24h, 2),
            "volume_7d_avg": round(vol_7d_avg, 2),
            "volume_ratio": round(ratio, 2),
            "reason": f"24h volume {ratio:.1f}x above 7-day average",
        }
        if is_tick_volume:
            details["note"] = "tick volume"
        return {
            "type": "volume_surge",
            "score": score,
            "details": details,
        }

    @staticmethod
    def _check_rsi_bounce(
        symbol: str,
        rsi_series: pd.Series,
        latest_close: float,
        timeframe: str,
    ) -> dict[str, Any] | None:
        """RSI crossed above 30 (oversold recovery) or below 70 (overbought rejection)."""
        if len(rsi_series) < 3:
            return None

        curr_rsi = float(rsi_series.iloc[-1])
        prev_rsi = float(rsi_series.iloc[-2])

        # Oversold bounce: crossed above 30
        if prev_rsi < 30 and curr_rsi >= 30:
            score = min(int(50 + (30 - prev_rsi) * 2), 85)
            return {
                "type": "rsi_bounce",
                "score": score,
                "details": {
                    "price": latest_close,
                    "rsi": round(curr_rsi, 1),
                    "prev_rsi": round(prev_rsi, 1),
                    "direction": "bullish",
                    "reason": f"RSI bounced from oversold ({prev_rsi:.0f} → {curr_rsi:.0f})",
                },
            }

        # Overbought rejection: crossed below 70
        if prev_rsi > 70 and curr_rsi <= 70:
            score = min(int(45 + (prev_rsi - 70) * 2), 80)
            return {
                "type": "rsi_bounce",
                "score": score,
                "details": {
                    "price": latest_close,
                    "rsi": round(curr_rsi, 1),
                    "prev_rsi": round(prev_rsi, 1),
                    "direction": "bearish",
                    "reason": f"RSI rejected from overbought ({prev_rsi:.0f} → {curr_rsi:.0f})",
                },
            }

        return None

    @staticmethod
    def _check_breakout(
        symbol: str,
        close: pd.Series,
        volume: pd.Series,
        sma_20: pd.Series,
        latest_close: float,
        timeframe: str,
        *,
        distance_pct: float = 2.0,
    ) -> dict[str, Any] | None:
        """Price within distance_pct of 20-day high with increasing volume."""
        if len(close) < 20:
            return None

        high_20d = float(close.iloc[-20:].max())
        dist = (high_20d - latest_close) / high_20d * 100

        if dist > distance_pct:
            return None

        # Check volume is increasing (last 5 bars avg vs previous 5)
        if len(volume) < 10:
            return None
        vol_recent = float(volume.iloc[-5:].mean())
        vol_prev = float(volume.iloc[-10:-5].mean())
        vol_increasing = vol_prev > 0 and vol_recent > vol_prev

        if not vol_increasing:
            return None

        vol_ratio = vol_recent / vol_prev if vol_prev > 0 else 1.0
        score = min(int(55 + (distance_pct - dist) * 10 + (vol_ratio - 1.0) * 10), 90)

        return {
            "type": "breakout",
            "score": score,
            "details": {
                "price": latest_close,
                "high_20d": round(high_20d, 6),
                "distance_pct": round(dist, 2),
                "volume_ratio": round(vol_ratio, 2),
                "reason": (
                    f"Price within {dist:.1f}% of 20-day high, "
                    f"volume up {vol_ratio:.1f}x"
                ),
            },
        }

    @staticmethod
    def _check_trend_pullback(
        symbol: str,
        close: pd.Series,
        adx_series: pd.Series,
        ema_50: pd.Series,
        latest_close: float,
        timeframe: str,
        *,
        pullback_min: float = 3.0,
        pullback_max: float = 5.0,
    ) -> dict[str, Any] | None:
        """Pullback in uptrend (ADX>25, above 50 EMA)."""
        if len(close) < 5 or adx_series.empty or ema_50.empty:
            return None

        latest_adx = float(adx_series.iloc[-1])
        latest_ema50 = float(ema_50.iloc[-1])

        if latest_adx < 25 or latest_close < latest_ema50:
            return None

        recent_high = float(close.iloc[-10:].max())
        pullback_pct = (recent_high - latest_close) / recent_high * 100

        if pullback_pct < pullback_min or pullback_pct > pullback_max:
            return None

        score = min(int(55 + latest_adx * 0.5 + pullback_pct * 3), 90)

        return {
            "type": "trend_pullback",
            "score": score,
            "details": {
                "price": latest_close,
                "adx": round(latest_adx, 1),
                "ema_50": round(latest_ema50, 6),
                "pullback_pct": round(pullback_pct, 2),
                "recent_high": round(recent_high, 6),
                "reason": (
                    f"Uptrend pullback {pullback_pct:.1f}% "
                    f"(ADX={latest_adx:.0f}, above EMA50)"
                ),
            },
        }

    @staticmethod
    def _check_momentum_shift(
        symbol: str,
        macd_df: pd.DataFrame,
        latest_close: float,
        timeframe: str,
    ) -> dict[str, Any] | None:
        """MACD histogram changed sign in last 2 candles."""
        if macd_df.empty or len(macd_df) < 3:
            return None

        hist_col = next(
            (c for c in ("macd_hist", "histogram", "hist") if c in macd_df.columns),
            None,
        )
        if hist_col is None:
            return None

        curr_hist = float(macd_df[hist_col].iloc[-1])
        prev_hist = float(macd_df[hist_col].iloc[-2])

        # Sign change
        if (curr_hist > 0 and prev_hist >= 0) or (curr_hist < 0 and prev_hist <= 0):
            return None

        direction = "bullish" if curr_hist > 0 else "bearish"
        strength = abs(curr_hist - prev_hist)
        score = min(int(45 + strength * 1000), 80)  # Scale up tiny histogram values

        return {
            "type": "momentum_shift",
            "score": score,
            "details": {
                "price": latest_close,
                "macd_histogram": round(curr_hist, 6),
                "prev_histogram": round(prev_hist, 6),
                "direction": direction,
                "reason": f"MACD histogram flipped {direction} ({prev_hist:.4f} → {curr_hist:.4f})",
            },
        }

    # ── Persistence with deduplication ──────────────────────────

    @staticmethod
    def _save_opportunity(
        model_cls: type,
        symbol: str,
        opp: dict[str, Any],
        asset_class: str,
        timeframe: str,
        expires_at: Any,
        now: Any,
        _max_retries: int = 3,
    ) -> bool:
        """Save or update an opportunity, deduplicating by (symbol, type, asset_class).

        Returns True if a new record was created, False if an existing one was updated.
        Uses transaction.atomic() with retry on SQLite OperationalError (database locked).
        """
        for attempt in range(_max_retries):
            try:
                with transaction.atomic():
                    _, created = model_cls.objects.update_or_create(
                        symbol=symbol,
                        opportunity_type=opp["type"],
                        asset_class=asset_class,
                        acted_on=False,
                        expires_at__gt=now,
                        defaults={
                            "score": opp["score"],
                            "details": opp["details"],
                            "timeframe": timeframe,
                            "expires_at": expires_at,
                        },
                    )
                return created
            except OperationalError:
                if attempt < _max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                else:
                    logger.error(
                        "Database locked saving opportunity %s/%s after %d retries",
                        symbol, opp["type"], _max_retries,
                    )
                    raise
        return False  # pragma: no cover

    # ── Score enrichment ─────────────────────────────────────────

    @staticmethod
    def _enrich_score(
        opp: dict[str, Any], rsi: float, adx_val: float,
    ) -> dict[str, Any]:
        """Add confluence bonus to score based on multiple indicator alignment."""
        bonus = 0
        confluences = []

        # RSI in favorable zone
        if 30 <= rsi <= 45:
            bonus += 5
            confluences.append("RSI oversold zone")
        elif 55 <= rsi <= 70:
            bonus += 3
            confluences.append("RSI momentum zone")

        # Strong trend
        if adx_val > 25:
            bonus += 5
            confluences.append(f"Strong trend (ADX={adx_val:.0f})")

        opp["score"] = min(opp["score"] + bonus, 100)
        if confluences:
            opp["details"]["confluences"] = confluences
        return opp

    # ── Alerts ───────────────────────────────────────────────────

    def _maybe_alert(self, symbol: str, opp: dict[str, Any], asset_class: str = "") -> None:
        """Broadcast WS event and optionally send Telegram for high-score opportunities."""
        score = opp["score"]

        if score >= self.HIGH_SCORE_WS_THRESHOLD:
            try:
                from core.services.ws_broadcast import broadcast_opportunity

                broadcast_opportunity(
                    symbol=symbol,
                    opportunity_type=opp["type"],
                    score=score,
                    details=opp["details"],
                )
            except Exception:
                logger.debug("Opportunity WS broadcast failed", exc_info=True)

        if score >= self.HIGH_SCORE_TELEGRAM_THRESHOLD:
            try:
                from core.services.notification import send_telegram_rate_limited

                ac_label = f" [{asset_class.upper()}]" if asset_class else ""
                msg = (
                    f"Market Opportunity{ac_label}: {symbol}\n"
                    f"Type: {opp['type'].replace('_', ' ').title()}\n"
                    f"Score: {score}/100\n"
                    f"{opp['details'].get('reason', '')}"
                )
                rate_key = f"opp:{symbol}:{opp['type']}"
                send_telegram_rate_limited(msg, rate_key)
            except Exception:
                logger.debug("Opportunity Telegram failed", exc_info=True)
