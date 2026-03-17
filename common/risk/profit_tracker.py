"""Profit reinvestment tracker for aggressive capital management.

Tracks base capital ($500), realized profits, and implements an 80/20
reinvestment split: 80% of profits are reinvested, 20% reserved.
Losses reduce the reinvested pool first, never below base capital.

State is persisted to JSON via atomic writes (os.replace).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BASE_CAPITAL = 500.0
REINVESTMENT_RATIO = 0.80  # 80% of profits reinvested
RESERVE_RATIO = 0.20  # 20% reserved
DEFAULT_STATE_PATH = "data/profit_tracker.json"


@dataclass
class ProfitState:
    """Snapshot of profit tracking state."""

    base_capital: float = DEFAULT_BASE_CAPITAL
    total_realized_pnl: float = 0.0
    reinvested_pool: float = 0.0  # Accumulated reinvested profits
    reserved_pool: float = 0.0  # Accumulated reserved profits
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    @property
    def current_budget(self) -> float:
        """Total trading budget: base capital + reinvested profits."""
        return max(self.base_capital, self.base_capital + self.reinvested_pool)

    @property
    def total_equity(self) -> float:
        """Total equity including reserves."""
        return self.base_capital + self.reinvested_pool + self.reserved_pool

    @property
    def win_rate(self) -> float:
        """Win rate as a fraction."""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades


class ProfitTracker:
    """Thread-safe profit reinvestment tracker with JSON persistence."""

    _instance: ProfitTracker | None = None
    _lock = threading.Lock()

    def __init__(self, state_path: str | Path | None = None) -> None:
        self._state_path = Path(state_path or DEFAULT_STATE_PATH)
        self._state = ProfitState()
        self._io_lock = threading.Lock()
        self._load()

    @classmethod
    def get_instance(cls, state_path: str | Path | None = None) -> ProfitTracker:
        """Thread-safe singleton."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(state_path)
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    def record_trade(self, pnl: float) -> None:
        """Record a completed trade's P&L and update pools.

        Profits are split 80/20 between reinvested and reserved pools.
        Losses reduce the reinvested pool first, never below zero
        (base capital is always protected).
        """
        with self._io_lock:
            self._state.total_realized_pnl += pnl
            self._state.total_trades += 1

            if pnl >= 0:
                self._state.winning_trades += 1
                self._state.largest_win = max(self._state.largest_win, pnl)
                # Split profit 80/20
                self._state.reinvested_pool += pnl * REINVESTMENT_RATIO
                self._state.reserved_pool += pnl * RESERVE_RATIO
            else:
                self._state.losing_trades += 1
                self._state.largest_loss = min(self._state.largest_loss, pnl)
                # Losses come from reinvested pool first
                self._state.reinvested_pool = max(
                    0.0, self._state.reinvested_pool + pnl,
                )

            self._save()

    def get_stake_multiplier(self) -> float:
        """Return ratio of current budget / base capital.

        Used to scale stake amounts as profits grow.
        Returns 1.0 at baseline, >1.0 when profitable, never <1.0.
        """
        with self._io_lock:
            return max(1.0, self._state.current_budget / self._state.base_capital)

    def get_state(self) -> ProfitState:
        """Return a copy of current state."""
        with self._io_lock:
            return ProfitState(**asdict(self._state))

    def get_summary(self) -> dict:
        """Return state as a JSON-serializable dict for API responses."""
        with self._io_lock:
            multiplier = max(1.0, self._state.current_budget / self._state.base_capital)
            return {
                "base_capital": self._state.base_capital,
                "current_budget": self._state.current_budget,
                "total_equity": self._state.total_equity,
                "total_realized_pnl": self._state.total_realized_pnl,
                "reinvested_pool": self._state.reinvested_pool,
                "reserved_pool": self._state.reserved_pool,
                "stake_multiplier": multiplier,
                "total_trades": self._state.total_trades,
                "winning_trades": self._state.winning_trades,
                "losing_trades": self._state.losing_trades,
                "win_rate": self._state.win_rate,
                "largest_win": self._state.largest_win,
                "largest_loss": self._state.largest_loss,
            }

    def _load(self) -> None:
        """Load state from JSON file."""
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text())
            self._state = ProfitState(
                base_capital=data.get("base_capital", DEFAULT_BASE_CAPITAL),
                total_realized_pnl=data.get("total_realized_pnl", 0.0),
                reinvested_pool=data.get("reinvested_pool", 0.0),
                reserved_pool=data.get("reserved_pool", 0.0),
                total_trades=data.get("total_trades", 0),
                winning_trades=data.get("winning_trades", 0),
                losing_trades=data.get("losing_trades", 0),
                largest_win=data.get("largest_win", 0.0),
                largest_loss=data.get("largest_loss", 0.0),
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load profit tracker state: %s", e)

    def _save(self) -> None:
        """Persist state to JSON via atomic write."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._state_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(asdict(self._state), indent=2))
            os.replace(str(tmp_path), str(self._state_path))
        except OSError as e:
            logger.error("Failed to save profit tracker state: %s", e)
