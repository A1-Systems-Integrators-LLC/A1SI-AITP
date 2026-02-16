"""
Crypto-Investor Risk Management Module
=======================================
Shared risk controls that wrap all framework tiers.
Enforces position sizing, drawdown limits, correlation checks,
VaR/CVaR estimation, and daily loss limits.
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

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


@dataclass
class VaRResult:
    """Value-at-Risk calculation result."""
    var_95: float = 0.0          # 95% VaR (dollar amount)
    var_99: float = 0.0          # 99% VaR (dollar amount)
    cvar_95: float = 0.0         # 95% Conditional VaR (Expected Shortfall)
    cvar_99: float = 0.0         # 99% Conditional VaR
    method: str = "parametric"   # parametric or historical
    window_days: int = 0         # number of return observations used


class ReturnTracker:
    """
    Tracks per-symbol return series for correlation and VaR calculations.

    Stores a rolling window of daily returns for each symbol that has been
    traded, enabling portfolio-level risk metrics.
    """

    def __init__(self, max_history: int = 252):
        self.max_history = max_history
        self._returns: dict[str, deque[float]] = {}
        self._prices: dict[str, deque[float]] = {}

    def record_price(self, symbol: str, price: float) -> None:
        """Record a price observation for a symbol."""
        if symbol not in self._prices:
            self._prices[symbol] = deque(maxlen=self.max_history + 1)
            self._returns[symbol] = deque(maxlen=self.max_history)

        prices = self._prices[symbol]
        prices.append(price)

        if len(prices) >= 2:
            ret = (prices[-1] - prices[-2]) / prices[-2]
            self._returns[symbol].append(ret)

    def get_returns(self, symbol: str) -> np.ndarray:
        """Get return series for a symbol."""
        if symbol not in self._returns:
            return np.array([])
        return np.array(self._returns[symbol])

    def get_correlation_matrix(self, symbols: Optional[list[str]] = None) -> pd.DataFrame:
        """
        Compute correlation matrix across tracked symbols.

        Only includes symbols with >= 20 return observations for statistical relevance.
        """
        if symbols is None:
            symbols = [s for s, r in self._returns.items() if len(r) >= 20]
        else:
            symbols = [s for s in symbols if s in self._returns and len(self._returns[s]) >= 20]

        if len(symbols) < 2:
            return pd.DataFrame()

        # Align return series by using the minimum shared length
        min_len = min(len(self._returns[s]) for s in symbols)
        data = {s: list(self._returns[s])[-min_len:] for s in symbols}
        df = pd.DataFrame(data)
        return df.corr()

    def compute_var(
        self,
        symbols_weights: dict[str, float],
        portfolio_value: float,
        method: str = "parametric",
    ) -> VaRResult:
        """
        Compute portfolio VaR and CVaR.

        Parameters
        ----------
        symbols_weights : dict
            {symbol: weight} where weight = position_value / portfolio_value
        portfolio_value : float
            Total portfolio value in base currency
        method : str
            'parametric' (Gaussian) or 'historical'

        Returns
        -------
        VaRResult with VaR and CVaR at 95% and 99% confidence
        """
        valid_symbols = [
            s for s in symbols_weights
            if s in self._returns and len(self._returns[s]) >= 20
        ]

        if not valid_symbols:
            return VaRResult(method=method)

        # Build aligned return matrix
        min_len = min(len(self._returns[s]) for s in valid_symbols)
        returns_data = {s: list(self._returns[s])[-min_len:] for s in valid_symbols}
        returns_df = pd.DataFrame(returns_data)
        weights = np.array([symbols_weights.get(s, 0.0) for s in valid_symbols])

        # Portfolio returns
        portfolio_returns = returns_df.values @ weights

        if method == "historical":
            sorted_returns = np.sort(portfolio_returns)
            n = len(sorted_returns)
            idx_95 = max(0, int(n * 0.05))
            idx_99 = max(0, int(n * 0.01))

            var_95 = -sorted_returns[idx_95] * portfolio_value
            var_99 = -sorted_returns[idx_99] * portfolio_value
            cvar_95 = -sorted_returns[:idx_95 + 1].mean() * portfolio_value if idx_95 > 0 else var_95
            cvar_99 = -sorted_returns[:idx_99 + 1].mean() * portfolio_value if idx_99 > 0 else var_99
        else:
            # Parametric (Gaussian) VaR
            mu = portfolio_returns.mean()
            sigma = portfolio_returns.std()
            if sigma == 0:
                return VaRResult(method=method, window_days=min_len)

            var_95 = -(mu + scipy_stats.norm.ppf(0.05) * sigma) * portfolio_value
            var_99 = -(mu + scipy_stats.norm.ppf(0.01) * sigma) * portfolio_value

            # CVaR = E[loss | loss > VaR] for Gaussian
            cvar_95 = (
                -(mu - sigma * scipy_stats.norm.pdf(scipy_stats.norm.ppf(0.05)) / 0.05)
                * portfolio_value
            )
            cvar_99 = (
                -(mu - sigma * scipy_stats.norm.pdf(scipy_stats.norm.ppf(0.01)) / 0.01)
                * portfolio_value
            )

        return VaRResult(
            var_95=round(var_95, 2),
            var_99=round(var_99, 2),
            cvar_95=round(cvar_95, 2),
            cvar_99=round(cvar_99, 2),
            method=method,
            window_days=min_len,
        )

    @property
    def tracked_symbols(self) -> list[str]:
        """Symbols with return data."""
        return list(self._returns.keys())


class RiskManager:
    """
    Centralized risk manager that gates all trade decisions.

    Usage:
        rm = RiskManager(limits=RiskLimits(max_portfolio_drawdown=0.10))
        rm.return_tracker.record_price("BTC/USDT", 50000)  # feed prices
        approved, reason = rm.check_new_trade(symbol, side, size, entry, stop_loss)
        if approved:
            execute_trade(...)
        else:
            logger.warning(f"Trade rejected: {reason}")
    """

    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()
        self.state = PortfolioState()
        self.return_tracker = ReturnTracker()
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
        regime_modifier: Optional[float] = None,
    ) -> float:
        """
        Calculate position size based on risk per trade.

        Uses the formula:
            position_size = (equity * risk_pct) / abs(entry - stop_loss)

        Parameters
        ----------
        regime_modifier : float | None
            Optional regime-based position sizing modifier (0-1).
            Applied after max position cap. From StrategyRouter.route().position_size_modifier.
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

        # Apply regime modifier after cap
        if regime_modifier is not None:
            clamped = max(0.0, min(1.0, regime_modifier))
            size *= clamped
            logger.info(
                f"Regime modifier applied: {clamped:.2f} → adjusted size {size:.6f}"
            )

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

            # Check min risk/reward ratio: reject if stop is so wide that
            # achieving min_risk_reward requires an unrealistic price move (>15%)
            if price_risk > 0:
                required_profit_pct = trade_risk * self.limits.min_risk_reward
                if required_profit_pct > 0.15:
                    return False, (
                        f"Risk/reward unfavorable: stop at {trade_risk:.2%} "
                        f"requires {required_profit_pct:.1%} profit for "
                        f"{self.limits.min_risk_reward}:1 R:R"
                    )

        # Check correlation with existing positions
        corr_ok, corr_reason = self._check_correlation(symbol)
        if not corr_ok:
            return False, corr_reason

        # All checks passed
        logger.info(f"Trade approved: {side} {size:.6f} {symbol} @ {entry_price}")
        return True, "approved"

    def _check_correlation(self, symbol: str) -> tuple[bool, str]:
        """Check if new symbol is too correlated with existing positions."""
        if not self.state.open_positions:
            return True, ""

        existing_symbols = list(self.state.open_positions.keys())
        all_symbols = existing_symbols + [symbol]

        corr_matrix = self.return_tracker.get_correlation_matrix(all_symbols)
        if corr_matrix.empty:
            # Not enough data to check — allow the trade but warn
            logger.info(f"Insufficient return history for correlation check on {symbol}")
            return True, ""

        if symbol not in corr_matrix.columns:
            return True, ""

        for existing in existing_symbols:
            if existing in corr_matrix.columns:
                corr = abs(corr_matrix.loc[symbol, existing])
                if corr > self.limits.max_correlation:
                    return False, (
                        f"Correlation too high: {symbol} vs {existing} = {corr:.2f} "
                        f"> {self.limits.max_correlation}"
                    )

        return True, ""

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

    def get_var(self, method: str = "parametric") -> VaRResult:
        """
        Compute portfolio VaR/CVaR based on current open positions.

        Requires return data to have been fed via return_tracker.record_price().
        """
        if not self.state.open_positions or self.state.total_equity <= 0:
            return VaRResult(method=method)

        weights = {}
        for symbol, pos in self.state.open_positions.items():
            weights[symbol] = pos["value"] / self.state.total_equity

        return self.return_tracker.compute_var(weights, self.state.total_equity, method)

    def portfolio_heat_check(self) -> dict:
        """
        Aggregate portfolio health assessment.

        Returns a dict with all risk metrics and an overall 'healthy' flag.
        Call before every trade to get a full picture.
        """
        status = self.get_status()
        drawdown = 1.0 - (self.state.total_equity / self.state.peak_equity) if self.state.peak_equity > 0 else 0.0

        # Correlation matrix for open positions
        open_symbols = list(self.state.open_positions.keys())
        corr_matrix = self.return_tracker.get_correlation_matrix(open_symbols)
        max_corr = 0.0
        high_corr_pairs = []
        if not corr_matrix.empty and len(corr_matrix) >= 2:
            for i, s1 in enumerate(corr_matrix.columns):
                for s2 in corr_matrix.columns[i + 1:]:
                    c = abs(corr_matrix.loc[s1, s2])
                    max_corr = max(max_corr, c)
                    if c > self.limits.max_correlation:
                        high_corr_pairs.append((s1, s2, round(c, 3)))

        # VaR
        var_result = self.get_var()

        # Position concentration
        position_pcts = {}
        for symbol, pos in self.state.open_positions.items():
            position_pcts[symbol] = pos["value"] / self.state.total_equity if self.state.total_equity > 0 else 0.0
        max_concentration = max(position_pcts.values()) if position_pcts else 0.0

        # Overall health
        issues = []
        if self.state.is_halted:
            issues.append(f"HALTED: {self.state.halt_reason}")
        if drawdown > self.limits.max_portfolio_drawdown * 0.8:
            issues.append(f"Drawdown warning: {drawdown:.2%} approaching limit {self.limits.max_portfolio_drawdown:.2%}")
        if high_corr_pairs:
            issues.append(f"High correlation: {high_corr_pairs}")
        if max_concentration > self.limits.max_position_size_pct * 0.9:
            issues.append(f"Concentration warning: {max_concentration:.2%} in single position")
        if var_result.var_99 > self.state.total_equity * 0.10:
            issues.append(f"VaR warning: 99% VaR ${var_result.var_99:.0f} > 10% of equity")

        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "drawdown": round(drawdown, 4),
            "daily_pnl": self.state.daily_pnl,
            "open_positions": len(self.state.open_positions),
            "max_correlation": round(max_corr, 3),
            "high_corr_pairs": high_corr_pairs,
            "max_concentration": round(max_concentration, 4),
            "position_weights": {k: round(v, 4) for k, v in position_pcts.items()},
            "var_95": var_result.var_95,
            "var_99": var_result.var_99,
            "cvar_95": var_result.cvar_95,
            "cvar_99": var_result.cvar_99,
            "is_halted": self.state.is_halted,
        }
