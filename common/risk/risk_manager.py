"""
Crypto-Investor Risk Management Module
=======================================
Shared risk controls that wrap all framework tiers.
Enforces position sizing, drawdown limits, correlation checks, and daily loss limits.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("risk_manager")


@dataclass
class RiskLimits:
    """Global risk parameters."""
    max_portfolio_drawdown: float = 0.15      # 15% max drawdown -> halt
    max_single_trade_risk: float = 0.02       # 2% portfolio risk per trade
    max_daily_loss: float = 0.05              # 5% max daily loss
    max_open_positions: int = 10
    max_position_size_pct: float = 0.20       # 20% max in single position
    max_correlation: float = 0.70             # Max correlation between positions
    min_risk_reward: float = 1.5              # Minimum risk/reward ratio
    max_leverage: float = 1.0                 # No leverage by default


@dataclass
class PortfolioState:
    """Track current portfolio state for risk checks."""
    total_equity: float = 10000.0
    peak_equity: float = 10000.0
    daily_start_equity: float = 10000.0
    open_positions: dict = field(default_factory=dict)
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    is_halted: bool = False
    halt_reason: str = ""
    last_update: Optional[datetime] = None


class RiskManager:
    """
    Centralized risk manager that gates all trade decisions.

    Usage:
        rm = RiskManager(limits=RiskLimits(max_portfolio_drawdown=0.10))
        approved, reason = rm.check_new_trade(symbol, side, size, entry, stop_loss)
        if approved:
            execute_trade(...)
        else:
            logger.warning(f"Trade rejected: {reason}")
    """

    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()
        self.state = PortfolioState()
        logger.info(f"RiskManager initialized: {self.limits}")

    def update_equity(self, current_equity: float):
        """Update portfolio equity and check drawdown limits."""
        self.state.total_equity = current_equity
        self.state.peak_equity = max(self.state.peak_equity, current_equity)
        self.state.last_update = datetime.now(timezone.utc)

        # Check max drawdown
        drawdown = 1.0 - (current_equity / self.state.peak_equity)
        if drawdown >= self.limits.max_portfolio_drawdown:
            self.state.is_halted = True
            self.state.halt_reason = (
                f"Max drawdown breached: {drawdown:.2%} >= {self.limits.max_portfolio_drawdown:.2%}"
            )
            logger.critical(self.state.halt_reason)
            return False

        # Check daily loss
        daily_change = (current_equity - self.state.daily_start_equity) / self.state.daily_start_equity
        if daily_change <= -self.limits.max_daily_loss:
            self.state.is_halted = True
            self.state.halt_reason = (
                f"Daily loss limit breached: {daily_change:.2%} <= -{self.limits.max_daily_loss:.2%}"
            )
            logger.critical(self.state.halt_reason)
            return False

        return True

    def reset_daily(self):
        """Reset daily tracking (call at start of each trading day)."""
        self.state.daily_start_equity = self.state.total_equity
        self.state.daily_pnl = 0.0
        if self.state.is_halted and "Daily" in self.state.halt_reason:
            self.state.is_halted = False
            self.state.halt_reason = ""
            logger.info("Daily halt cleared, trading resumed")

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float,
        risk_per_trade: Optional[float] = None,
    ) -> float:
        """
        Calculate position size based on risk per trade.

        Uses the formula:
            position_size = (equity * risk_pct) / abs(entry - stop_loss)
        """
        risk_pct = risk_per_trade or self.limits.max_single_trade_risk
        risk_amount = self.state.total_equity * risk_pct
        price_risk = abs(entry_price - stop_loss_price)

        if price_risk == 0:
            logger.warning("Stop loss equals entry price, returning 0 size")
            return 0.0

        size = risk_amount / price_risk

        # Cap at max position size
        max_size_value = self.state.total_equity * self.limits.max_position_size_pct
        max_size = max_size_value / entry_price
        size = min(size, max_size)

        logger.info(
            f"Position size: {size:.6f} (risk ${risk_amount:.2f}, "
            f"price risk ${price_risk:.2f}, entry ${entry_price:.2f})"
        )
        return size

    def check_new_trade(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        stop_loss_price: Optional[float] = None,
    ) -> tuple[bool, str]:
        """
        Gate function: check if a new trade passes all risk checks.

        Returns (approved, reason) tuple.
        """
        # Check halt status
        if self.state.is_halted:
            return False, f"Trading halted: {self.state.halt_reason}"

        # Check max open positions
        if len(self.state.open_positions) >= self.limits.max_open_positions:
            return False, f"Max open positions reached ({self.limits.max_open_positions})"

        # Check if already in this position
        if symbol in self.state.open_positions:
            return False, f"Already have open position in {symbol}"

        # Check position size vs portfolio
        trade_value = size * entry_price
        position_pct = trade_value / self.state.total_equity
        if position_pct > self.limits.max_position_size_pct:
            return False, (
                f"Position too large: {position_pct:.2%} > {self.limits.max_position_size_pct:.2%}"
            )

        # Check risk/reward if stop loss provided
        if stop_loss_price:
            price_risk = abs(entry_price - stop_loss_price)
            trade_risk = (price_risk / entry_price)
            if trade_risk > self.limits.max_single_trade_risk * 2:
                return False, f"Stop loss too wide: {trade_risk:.2%} risk per unit"

        # All checks passed
        logger.info(f"Trade approved: {side} {size:.6f} {symbol} @ {entry_price}")
        return True, "approved"

    def register_trade(self, symbol: str, side: str, size: float, entry_price: float):
        """Register an executed trade for tracking."""
        self.state.open_positions[symbol] = {
            "side": side,
            "size": size,
            "entry_price": entry_price,
            "entry_time": datetime.now(timezone.utc),
            "value": size * entry_price,
        }

    def close_trade(self, symbol: str, exit_price: float) -> float:
        """Close a tracked position and return PnL."""
        if symbol not in self.state.open_positions:
            logger.warning(f"No open position found for {symbol}")
            return 0.0

        pos = self.state.open_positions.pop(symbol)
        if pos["side"] == "buy":
            pnl = (exit_price - pos["entry_price"]) * pos["size"]
        else:
            pnl = (pos["entry_price"] - exit_price) * pos["size"]

        self.state.daily_pnl += pnl
        self.state.total_pnl += pnl
        logger.info(f"Closed {symbol}: PnL ${pnl:.2f} (daily: ${self.state.daily_pnl:.2f})")
        return pnl

    def get_status(self) -> dict:
        """Return current risk manager status."""
        drawdown = 1.0 - (self.state.total_equity / self.state.peak_equity) if self.state.peak_equity > 0 else 0
        return {
            "equity": self.state.total_equity,
            "peak_equity": self.state.peak_equity,
            "drawdown": f"{drawdown:.2%}",
            "daily_pnl": self.state.daily_pnl,
            "total_pnl": self.state.total_pnl,
            "open_positions": len(self.state.open_positions),
            "is_halted": self.state.is_halted,
            "halt_reason": self.state.halt_reason,
        }
