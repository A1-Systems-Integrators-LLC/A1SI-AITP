"""Strategy Orchestrator — regime-aware strategy pause/resume management.

Evaluates regime-strategy alignment and maintains a thread-safe state store
of which strategies should be active, paused, or size-reduced. Integrates
with AlertLog, WebSocket broadcasts, and Telegram notifications.

The orchestrator is invoked periodically by the ``strategy_orchestration``
scheduled task and its state is queried by Freqtrade strategies via the
``/api/analysis/signals/strategy-status/`` endpoint.
"""

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Actions the orchestrator can assign to a strategy
ACTION_ACTIVE = "active"
ACTION_PAUSE = "pause"
ACTION_REDUCE_SIZE = "reduce_size"


@dataclass
class StrategyState:
    """Snapshot of a single strategy's orchestrator decision."""

    strategy: str
    asset_class: str
    regime: str
    alignment: int
    action: str  # active | pause | reduce_size
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class StrategyOrchestrator:
    """Thread-safe strategy orchestration engine.

    Evaluates regime-strategy alignment for all asset classes, persists
    decisions in memory, logs to AlertLog, broadcasts via WebSocket,
    and sends Telegram notifications on state transitions.
    """

    _instance: "StrategyOrchestrator | None" = None
    _lock = threading.Lock()

    STRATEGY_MAP: dict[str, list[str]] = {
        "crypto": ["CryptoInvestorV1", "BollingerMeanReversion", "VolatilityBreakout"],
        "equity": ["EquityMomentum", "EquityMeanReversion"],
        "forex": ["ForexTrend", "ForexRange"],
    }

    REP_SYMBOLS: dict[str, str] = {
        "crypto": "BTC/USDT",
        "equity": "SPY",
        "forex": "EUR/USD",
    }

    # Alignment thresholds
    PAUSE_THRESHOLD = 15
    REDUCE_THRESHOLD = 35

    # Persistence path for state snapshot
    _STATE_FILE = Path(__file__).resolve().parents[2] / "data" / "orchestrator_state.json"

    def __init__(self) -> None:
        self._states: dict[str, StrategyState] = {}  # key: "strategy:asset_class"
        self._state_lock = threading.Lock()
        self._load_state()

    def _load_state(self) -> None:
        """Load persisted state from JSON file on startup."""
        try:
            if self._STATE_FILE.exists():
                data = json.loads(self._STATE_FILE.read_text())
                for key, entry in data.items():
                    self._states[key] = StrategyState(
                        strategy=entry["strategy"],
                        asset_class=entry["asset_class"],
                        regime=entry["regime"],
                        alignment=entry["alignment"],
                        action=entry["action"],
                        updated_at=datetime.fromisoformat(entry["updated_at"]),
                    )
                logger.info("Loaded %d orchestrator states from disk", len(self._states))
        except Exception as e:
            logger.warning("Could not load orchestrator state: %s", e)

    def _save_state(self) -> None:
        """Persist current state to JSON file."""
        try:
            self._STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            with self._state_lock:
                for key, state in self._states.items():
                    d = asdict(state)
                    d["updated_at"] = state.updated_at.isoformat()
                    data[key] = d
            tmp = self._STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(self._STATE_FILE)
        except Exception as e:
            logger.warning("Could not save orchestrator state: %s", e)

    @classmethod
    def get_instance(cls) -> "StrategyOrchestrator":
        """Get or create singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    def _state_key(self, strategy: str, asset_class: str) -> str:
        return f"{strategy}:{asset_class}"

    def get_state(self, strategy: str, asset_class: str) -> StrategyState | None:
        """Get the current state for a strategy."""
        with self._state_lock:
            return self._states.get(self._state_key(strategy, asset_class))

    def get_all_states(self) -> list[StrategyState]:
        """Get all strategy states."""
        with self._state_lock:
            return list(self._states.values())

    def is_paused(self, strategy: str, asset_class: str = "crypto") -> bool:
        """Check if a strategy is paused. Returns False (active) if unknown."""
        state = self.get_state(strategy, asset_class)
        if state is None:
            return False
        return state.action == ACTION_PAUSE

    def get_size_modifier(self, strategy: str, asset_class: str = "crypto") -> float:
        """Get position size modifier: 1.0 (active), 0.5 (reduce_size), 0.0 (pause)."""
        state = self.get_state(strategy, asset_class)
        if state is None:
            return 1.0
        if state.action == ACTION_PAUSE:
            return 0.0
        if state.action == ACTION_REDUCE_SIZE:
            return 0.5
        return 1.0

    @staticmethod
    def _load_regime_data(symbol: str, asset_class: str):
        """Load OHLCV DataFrame for regime detection."""
        from common.data_pipeline.pipeline import load_ohlcv

        exchange_id = "yfinance" if asset_class in ("equity", "forex") else "kraken"
        return load_ohlcv(symbol, "1h", exchange_id)

    def evaluate(
        self,
        asset_classes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate regime-strategy alignment and update states.

        Returns a list of result dicts for each strategy evaluated.
        Logs transitions to AlertLog, broadcasts via WS, and sends
        Telegram for pause events.
        """
        if asset_classes is None:
            asset_classes = ["crypto", "equity", "forex"]

        all_results: list[dict[str, Any]] = []

        for asset_class in asset_classes:
            strategies = self.STRATEGY_MAP.get(asset_class, [])
            sym = self.REP_SYMBOLS.get(asset_class, "BTC/USDT")

            try:
                from core.platform_bridge import ensure_platform_imports

                ensure_platform_imports()
                from common.regime.regime_detector import RegimeDetector
                from common.signals.constants import ALIGNMENT_TABLES

                detector = RegimeDetector()
                df = self._load_regime_data(sym, asset_class)
                if df is None or df.empty:
                    raise ValueError(f"No OHLCV data for {sym}")
                state = detector.detect(df)
                table = ALIGNMENT_TABLES.get(asset_class, ALIGNMENT_TABLES["crypto"])
                regime_row = table.get(state.regime, {})

                for strat in strategies:
                    alignment = regime_row.get(strat, 50)
                    action = self._classify_action(alignment)
                    result = self._update_strategy(
                        strat, asset_class, state.regime.value, alignment, action,
                    )
                    all_results.append(result)

            except Exception as e:
                logger.error("Strategy orchestration failed for %s: %s", asset_class, e)
                # Preserve existing state on error — do NOT un-pause strategies.
                # If no prior state exists (first run), default to active.
                for strat in strategies:
                    key = self._state_key(strat, asset_class)
                    existing = self._states.get(key)
                    if existing:
                        # Keep whatever state was already set
                        all_results.append({
                            "strategy": strat,
                            "asset_class": asset_class,
                            "regime": existing.regime,
                            "alignment": existing.alignment,
                            "action": existing.action,
                            "changed": False,
                            "error": str(e),
                        })
                    else:
                        # First run, no prior state — safe to default active
                        result = self._update_strategy(
                            strat, asset_class, "unknown", 50, ACTION_ACTIVE,
                        )
                        result["error"] = str(e)
                        result["changed"] = False
                        all_results.append(result)

        return all_results

    def _classify_action(self, alignment: int) -> str:
        """Convert alignment score to action."""
        if alignment <= self.PAUSE_THRESHOLD:
            return ACTION_PAUSE
        if alignment <= self.REDUCE_THRESHOLD:
            return ACTION_REDUCE_SIZE
        return ACTION_ACTIVE

    def _update_strategy(
        self,
        strategy: str,
        asset_class: str,
        regime: str,
        alignment: int,
        action: str,
    ) -> dict[str, Any]:
        """Update strategy state and handle transitions."""
        key = self._state_key(strategy, asset_class)

        with self._state_lock:
            previous = self._states.get(key)
            previous_action = previous.action if previous else ACTION_ACTIVE

            new_state = StrategyState(
                strategy=strategy,
                asset_class=asset_class,
                regime=regime,
                alignment=alignment,
                action=action,
            )
            self._states[key] = new_state

        # Persist to disk after every evaluation
        self._save_state()

        # Detect transition
        transitioned = previous_action != action

        if transitioned:
            self._on_transition(strategy, asset_class, regime, alignment, previous_action, action)

        return {
            "strategy": strategy,
            "asset_class": asset_class,
            "regime": regime,
            "alignment": alignment,
            "action": action,
            "transitioned": transitioned,
            "previous_action": previous_action,
        }

    def _on_transition(
        self,
        strategy: str,
        asset_class: str,
        regime: str,
        alignment: int,
        previous_action: str,
        new_action: str,
    ) -> None:
        """Handle a state transition — log, broadcast, notify."""
        msg = (
            f"Strategy {strategy} ({asset_class}): "
            f"{previous_action} → {new_action} "
            f"(regime={regime}, alignment={alignment})"
        )
        logger.info("Orchestrator transition: %s", msg)

        # AlertLog
        self._log_alert(strategy, asset_class, regime, alignment, previous_action, new_action)

        # WebSocket broadcast
        self._broadcast(strategy, asset_class, regime, alignment, new_action)

        # Telegram for pause transitions
        if new_action == ACTION_PAUSE:
            self._notify_telegram(
                f"⚠️ Strategy PAUSED: {strategy} ({asset_class}) — "
                f"regime={regime}, alignment={alignment}",
            )
        elif previous_action == ACTION_PAUSE and new_action == ACTION_ACTIVE:
            self._notify_telegram(
                f"✅ Strategy RESUMED: {strategy} ({asset_class}) — "
                f"regime={regime}, alignment={alignment}",
            )

    def _log_alert(
        self,
        strategy: str,
        asset_class: str,
        regime: str,
        alignment: int,
        previous_action: str,
        new_action: str,
    ) -> None:
        """Log transition to AlertLog model."""
        try:
            from risk.models import AlertLog

            severity = "warning" if new_action == ACTION_PAUSE else "info"
            AlertLog.objects.create(
                portfolio_id=0,
                event_type="strategy_orchestration",
                severity=severity,
                message=(
                    f"{strategy} ({asset_class}): {previous_action} → {new_action} "
                    f"| regime={regime}, alignment={alignment}"
                ),
                channel="log",
                delivered=True,
            )
        except Exception as e:
            logger.warning("Failed to log orchestrator alert: %s", e)

    def _broadcast(
        self,
        strategy: str,
        asset_class: str,
        regime: str,
        alignment: int,
        action: str,
    ) -> None:
        """Broadcast strategy status change via WebSocket."""
        try:
            from core.services.ws_broadcast import broadcast_strategy_status

            broadcast_strategy_status(
                strategy=strategy,
                asset_class=asset_class,
                regime=regime,
                alignment=alignment,
                action=action,
            )
        except Exception as e:
            logger.debug("WS broadcast failed for strategy status: %s", e)

    def _notify_telegram(self, message: str) -> None:
        """Send Telegram notification (rate-limited)."""
        try:
            from core.services.notification import send_telegram_rate_limited

            send_telegram_rate_limited(
                message,
                rate_key=f"orchestrator:{message[:30]}",
                cooldown=900,  # 15 min cooldown per message type
            )
        except Exception:
            pass
