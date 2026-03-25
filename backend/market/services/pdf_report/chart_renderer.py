"""Chart renderer for PDF reports.

Generates charts as base64-encoded PNG strings for embedding in HTML reports.
Uses matplotlib with Agg backend (headless).
"""

from __future__ import annotations

import base64
import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------
BG_COLOR = "#1a1a2e"
TEXT_COLOR = "#e0e0e0"
GRID_COLOR = "#333355"
GREEN = "#00d4aa"
RED = "#ff4757"
ACCENT = "#4ecdc4"

REGIME_COLORS: dict[str, str] = {
    "strong_trend_up": "#00d4aa",
    "weak_trend_up": "#4ecdc4",
    "ranging": "#ffd93d",
    "weak_trend_down": "#ff9f43",
    "strong_trend_down": "#ff4757",
    "high_volatility": "#a855f7",
    "unknown": "#666666",
}


def _apply_dark_theme(fig: plt.Figure, ax: plt.Axes) -> None:
    """Apply the standard dark theme to a figure and axes."""
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    ax.tick_params(colors=TEXT_COLOR, which="both")
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    ax.title.set_color(TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.grid(True, color=GRID_COLOR, alpha=0.5, linewidth=0.5)


def _fig_to_base64(fig: plt.Figure, dpi: int = 150) -> str:
    """Render a matplotlib figure to a base64-encoded PNG data URI."""
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=dpi,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)
    buf.seek(0)
    return f"data:image/png;base64,{base64.b64encode(buf.read()).decode()}"


class ReportChartRenderer:
    """Static methods that produce base64-encoded PNG chart strings."""

    @staticmethod
    def equity_curve(equity_history: list[dict]) -> str:
        """Line chart of equity over time.

        Args:
            equity_history: list of {"recorded_at": "ISO datetime", "total_equity": float}

        Returns:
            Base64 data URI string, or empty string if data is insufficient.
        """
        if not equity_history or len(equity_history) < 2:
            return ""

        dates = []
        values = []
        for point in equity_history:
            try:
                dt = datetime.fromisoformat(str(point.get("recorded_at") or point.get("timestamp", "")))
                dates.append(dt)
                values.append(float(point.get("total_equity") or point.get("equity", 0)))
            except (KeyError, ValueError, TypeError):
                continue

        if len(dates) < 2:
            return ""

        fig, ax = plt.subplots(figsize=(10, 3))
        _apply_dark_theme(fig, ax)

        ax.plot(dates, values, color=GREEN, linewidth=1.5)
        ax.fill_between(dates, values, alpha=0.15, color=GREEN)
        ax.set_ylabel("Equity ($)", color=TEXT_COLOR)
        ax.set_title("Portfolio Equity Curve", color=TEXT_COLOR, fontsize=12)
        fig.autofmt_xdate()

        return _fig_to_base64(fig)

    @staticmethod
    def daily_pnl_bars(daily_pnl: list[dict]) -> str:
        """Bar chart of daily P&L.

        Args:
            daily_pnl: list of {"date": "YYYY-MM-DD", "pnl": float}

        Returns:
            Base64 data URI string, or empty string if data is insufficient.
        """
        if not daily_pnl:
            return ""

        dates = []
        pnls = []
        for entry in daily_pnl:
            try:
                dates.append(str(entry["date"]))
                pnls.append(float(entry["pnl"]))
            except (KeyError, ValueError, TypeError):
                continue

        if not dates:
            return ""

        fig, ax = plt.subplots(figsize=(10, 3))
        _apply_dark_theme(fig, ax)

        colors = [GREEN if p >= 0 else RED for p in pnls]
        x_positions = range(len(dates))
        ax.bar(x_positions, pnls, color=colors, width=0.8)

        # Show a subset of date labels to avoid overlap
        step = max(1, len(dates) // 15)
        ax.set_xticks([i for i in x_positions if i % step == 0])
        ax.set_xticklabels(
            [dates[i] for i in range(len(dates)) if i % step == 0],
            rotation=45,
            ha="right",
            fontsize=7,
        )
        ax.axhline(y=0, color=TEXT_COLOR, linewidth=0.5, alpha=0.5)
        ax.set_ylabel("P&L ($)", color=TEXT_COLOR)
        ax.set_title("Daily P&L", color=TEXT_COLOR, fontsize=12)

        return _fig_to_base64(fig)

    @staticmethod
    def strategy_comparison(strategies: list[dict]) -> str:
        """Grouped bar chart comparing strategies across three metrics.

        Args:
            strategies: list of {"name": str, "pnl": float, "trades": int, "win_rate": float}

        Returns:
            Base64 data URI string, or empty string if data is insufficient.
        """
        if not strategies:
            return ""

        names = []
        pnls = []
        trades = []
        win_rates = []
        for s in strategies:
            try:
                names.append(str(s.get("name", "?")))
                pnls.append(float(s.get("pnl", 0)))
                tc = int(s.get("trade_count", 0) or s.get("trades", 0))
                trades.append(tc)
                wins = int(s.get("winning_trades", 0))
                wr = (wins / tc * 100) if tc > 0 else 0.0
                win_rates.append(float(s.get("win_rate", wr)))
            except (ValueError, TypeError):
                continue

        if not names:
            return ""

        fig, axes = plt.subplots(1, 3, figsize=(10, 4))
        fig.patch.set_facecolor(BG_COLOR)

        metric_data = [
            ("P&L ($)", pnls, GREEN),
            ("Trades", trades, ACCENT),
            ("Win Rate (%)", win_rates, "#a855f7"),
        ]

        for ax, (label, data, color) in zip(axes, metric_data):
            ax.set_facecolor(BG_COLOR)
            ax.tick_params(colors=TEXT_COLOR, which="both")
            for spine in ax.spines.values():
                spine.set_color(GRID_COLOR)
            ax.grid(True, color=GRID_COLOR, alpha=0.5, linewidth=0.5, axis="y")

            bar_colors = [GREEN if v >= 0 else RED for v in data] if label == "P&L ($)" else [color] * len(data)
            ax.bar(names, data, color=bar_colors, width=0.6)
            ax.set_title(label, color=TEXT_COLOR, fontsize=10)
            ax.tick_params(axis="x", rotation=30)
            for tick_label in ax.get_xticklabels():
                tick_label.set_fontsize(7)

        fig.suptitle("Strategy Comparison", color=TEXT_COLOR, fontsize=12, y=1.02)
        fig.tight_layout()

        return _fig_to_base64(fig)

    @staticmethod
    def regime_timeline(regime_data: list[dict]) -> str:
        """Horizontal color bands showing market regime over time.

        Args:
            regime_data: list of {"date": "YYYY-MM-DD", "regime": str}

        Returns:
            Base64 data URI string, or empty string if data is insufficient.
        """
        if not regime_data or len(regime_data) < 2:
            return ""

        dates = []
        regimes = []
        for entry in regime_data:
            try:
                dates.append(str(entry["date"]))
                regimes.append(str(entry["regime"]).lower())
            except (KeyError, TypeError):
                continue

        if len(dates) < 2:
            return ""

        fig, ax = plt.subplots(figsize=(10, 2))
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        ax.tick_params(colors=TEXT_COLOR, which="both")
        for spine in ax.spines.values():
            spine.set_color(GRID_COLOR)

        # Draw color bands
        for i in range(len(dates) - 1):
            regime = regimes[i]
            color = REGIME_COLORS.get(regime, REGIME_COLORS["unknown"])
            ax.axvspan(i, i + 1, facecolor=color, alpha=0.7)

        # Final band
        last_regime = regimes[-1]
        last_color = REGIME_COLORS.get(last_regime, REGIME_COLORS["unknown"])
        ax.axvspan(len(dates) - 1, len(dates), facecolor=last_color, alpha=0.7)

        # Date labels
        step = max(1, len(dates) // 15)
        ax.set_xticks([i for i in range(len(dates)) if i % step == 0])
        ax.set_xticklabels(
            [dates[i] for i in range(len(dates)) if i % step == 0],
            rotation=45,
            ha="right",
            fontsize=7,
        )
        ax.set_yticks([])
        ax.set_xlim(0, len(dates))
        ax.set_title("Market Regime Timeline", color=TEXT_COLOR, fontsize=12)

        # Legend
        from matplotlib.patches import Patch

        legend_elements = [
            Patch(facecolor=color, label=name.replace("_", " ").title())
            for name, color in REGIME_COLORS.items()
        ]
        legend = ax.legend(
            handles=legend_elements,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.35),
            ncol=4,
            fontsize=7,
            frameon=False,
        )
        for text in legend.get_texts():
            text.set_color(TEXT_COLOR)

        return _fig_to_base64(fig)

    @staticmethod
    def signal_source_radar(source_accuracy: dict) -> str:
        """Radar/spider chart showing accuracy per signal source.

        Args:
            source_accuracy: dict like {"technical": {"accuracy": 56}, "ml": {"accuracy": 52}, ...}

        Returns:
            Base64 data URI string, or empty string if data is insufficient.
        """
        if not source_accuracy:
            return ""

        labels = []
        values = []
        for source, data in source_accuracy.items():
            try:
                accuracy = float(data.get("accuracy", 0)) if isinstance(data, dict) else float(data)
                labels.append(str(source).replace("_", " ").title())
                values.append(accuracy)
            except (ValueError, TypeError, AttributeError):
                continue

        if len(labels) < 3:
            return ""

        num_vars = len(labels)
        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        # Close the polygon
        values_closed = values + [values[0]]
        angles_closed = angles + [angles[0]]

        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={"polar": True})
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)

        ax.plot(angles_closed, values_closed, color=GREEN, linewidth=2)
        ax.fill(angles_closed, values_closed, color=GREEN, alpha=0.2)

        ax.set_xticks(angles)
        ax.set_xticklabels(labels, color=TEXT_COLOR, fontsize=9)
        ax.set_ylim(0, 100)
        ax.set_yticks([20, 40, 60, 80, 100])
        ax.set_yticklabels(["20", "40", "60", "80", "100"], color=TEXT_COLOR, fontsize=7)
        ax.yaxis.grid(True, color=GRID_COLOR, alpha=0.5)
        ax.xaxis.grid(True, color=GRID_COLOR, alpha=0.5)
        ax.spines["polar"].set_color(GRID_COLOR)

        ax.set_title(
            "Signal Source Accuracy",
            color=TEXT_COLOR,
            fontsize=12,
            pad=20,
        )

        return _fig_to_base64(fig)

    @staticmethod
    def drawdown_chart(equity_history: list[dict]) -> str:
        """Drawdown chart computed from equity curve (equity vs running peak).

        Args:
            equity_history: list of {"recorded_at": "ISO datetime", "total_equity": float}

        Returns:
            Base64 data URI string, or empty string if data is insufficient.
        """
        if not equity_history or len(equity_history) < 2:
            return ""

        dates = []
        values = []
        for point in equity_history:
            try:
                dt = datetime.fromisoformat(str(point.get("recorded_at") or point.get("timestamp", "")))
                dates.append(dt)
                values.append(float(point.get("total_equity") or point.get("equity", 0)))
            except (KeyError, ValueError, TypeError):
                continue

        if len(dates) < 2:
            return ""

        equity_arr = np.array(values)
        running_peak = np.maximum.accumulate(equity_arr)
        drawdown_pct = np.where(
            running_peak > 0,
            ((equity_arr - running_peak) / running_peak) * 100,
            0.0,
        )

        fig, ax = plt.subplots(figsize=(10, 2.5))
        _apply_dark_theme(fig, ax)

        ax.fill_between(dates, drawdown_pct, 0, color=RED, alpha=0.5)
        ax.plot(dates, drawdown_pct, color=RED, linewidth=1)
        ax.axhline(y=0, color=TEXT_COLOR, linewidth=0.5, alpha=0.5)
        ax.set_ylabel("Drawdown (%)", color=TEXT_COLOR)
        ax.set_title("Portfolio Drawdown", color=TEXT_COLOR, fontsize=12)
        fig.autofmt_xdate()

        return _fig_to_base64(fig)
