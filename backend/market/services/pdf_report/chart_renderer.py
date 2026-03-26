"""Chart renderer for PDF reports.

Generates charts as base64-encoded PNG strings for embedding in HTML reports.
Uses matplotlib with Agg backend (headless). Light theme for print-friendly output.
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
# Light theme style constants (print-friendly)
# ---------------------------------------------------------------------------
BG_COLOR = "#ffffff"
TEXT_COLOR = "#1a1a2e"
GRID_COLOR = "#e0e0e8"
GREEN = "#0d7c5f"
RED = "#c0392b"
ACCENT = "#2980b9"
BLUE = "#2563eb"
PURPLE = "#7c3aed"
ORANGE = "#d97706"
TEAL = "#0891b2"

REGIME_COLORS: dict[str, str] = {
    "strong_trend_up": "#0d7c5f",
    "weak_trend_up": "#27ae60",
    "ranging": "#d4a017",
    "weak_trend_down": "#e67e22",
    "strong_trend_down": "#c0392b",
    "high_volatility": "#8e44ad",
    "unknown": "#95a5a6",
}

# Specialist colors for team assessment charts
SPECIALIST_COLORS = {
    "quant": "#2563eb",
    "strategy": "#0d7c5f",
    "risk": "#c0392b",
    "data": "#d97706",
    "ml": "#7c3aed",
    "market": "#0891b2",
}


def _apply_light_theme(fig: plt.Figure, ax: plt.Axes) -> None:
    """Apply the standard light theme to a figure and axes."""
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    ax.tick_params(colors=TEXT_COLOR, which="both", labelsize=8)
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    ax.title.set_color(TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.grid(True, color=GRID_COLOR, alpha=0.6, linewidth=0.5)


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
        """Line chart of equity over time."""
        if not equity_history or len(equity_history) < 2:
            return ""

        dates = []
        values = []
        for point in equity_history:
            try:
                raw = point.get("recorded_at") or point.get("timestamp", "")
                dt = datetime.fromisoformat(str(raw))
                dates.append(dt)
                eq = point.get("total_equity") or point.get("equity", 0)
                values.append(float(eq))
            except (KeyError, ValueError, TypeError):
                continue

        if len(dates) < 2:
            return ""

        fig, ax = plt.subplots(figsize=(10, 3))
        _apply_light_theme(fig, ax)

        ax.plot(dates, values, color=BLUE, linewidth=1.5)
        ax.fill_between(dates, values, alpha=0.08, color=BLUE)
        ax.set_ylabel("Equity ($)", color=TEXT_COLOR, fontsize=9)
        ax.set_title("Portfolio Equity Curve", color=TEXT_COLOR, fontsize=11, fontweight="bold")
        fig.autofmt_xdate()

        return _fig_to_base64(fig)

    @staticmethod
    def daily_pnl_bars(daily_pnl: list[dict]) -> str:
        """Bar chart of daily P&L."""
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
        _apply_light_theme(fig, ax)

        colors = [GREEN if p >= 0 else RED for p in pnls]
        x_positions = range(len(dates))
        ax.bar(x_positions, pnls, color=colors, width=0.8, edgecolor="white", linewidth=0.3)

        step = max(1, len(dates) // 15)
        ax.set_xticks([i for i in x_positions if i % step == 0])
        ax.set_xticklabels(
            [dates[i] for i in range(len(dates)) if i % step == 0],
            rotation=45,
            ha="right",
            fontsize=7,
        )
        ax.axhline(y=0, color=TEXT_COLOR, linewidth=0.5, alpha=0.3)
        ax.set_ylabel("P&L ($)", color=TEXT_COLOR, fontsize=9)
        ax.set_title("Daily P&L", color=TEXT_COLOR, fontsize=11, fontweight="bold")

        return _fig_to_base64(fig)

    @staticmethod
    def strategy_comparison(strategies: list[dict]) -> str:
        """Grouped bar chart comparing strategies across three metrics."""
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
            ("P&L ($)", pnls, BLUE),
            ("Trades", trades, TEAL),
            ("Win Rate (%)", win_rates, PURPLE),
        ]

        for ax, (label, data, color) in zip(axes, metric_data, strict=False):
            ax.set_facecolor(BG_COLOR)
            ax.tick_params(colors=TEXT_COLOR, which="both", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(GRID_COLOR)
            ax.grid(True, color=GRID_COLOR, alpha=0.6, linewidth=0.5, axis="y")

            if label == "P&L ($)":
                bar_colors = [GREEN if v >= 0 else RED for v in data]
            else:
                bar_colors = [color] * len(data)
            ax.bar(names, data, color=bar_colors, width=0.6, edgecolor="white", linewidth=0.3)
            ax.set_title(label, color=TEXT_COLOR, fontsize=10, fontweight="bold")
            ax.tick_params(axis="x", rotation=30)
            for tick_label in ax.get_xticklabels():
                tick_label.set_fontsize(7)

        fig.suptitle(
            "Strategy Comparison",
            color=TEXT_COLOR, fontsize=12, fontweight="bold", y=1.02,
        )
        fig.tight_layout()

        return _fig_to_base64(fig)

    @staticmethod
    def regime_timeline(regime_data: list[dict]) -> str:
        """Horizontal color bands showing market regime over time."""
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

        for i in range(len(dates) - 1):
            regime = regimes[i]
            color = REGIME_COLORS.get(regime, REGIME_COLORS["unknown"])
            ax.axvspan(i, i + 1, facecolor=color, alpha=0.7)

        last_regime = regimes[-1]
        last_color = REGIME_COLORS.get(last_regime, REGIME_COLORS["unknown"])
        ax.axvspan(len(dates) - 1, len(dates), facecolor=last_color, alpha=0.7)

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
        ax.set_title("Market Regime Timeline", color=TEXT_COLOR, fontsize=11, fontweight="bold")

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
        """Radar/spider chart showing accuracy per signal source."""
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
        values_closed = values + [values[0]]
        angles_closed = angles + [angles[0]]

        fig, ax = plt.subplots(figsize=(5, 5), subplot_kw={"polar": True})
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)

        ax.plot(angles_closed, values_closed, color=BLUE, linewidth=2)
        ax.fill(angles_closed, values_closed, color=BLUE, alpha=0.15)

        ax.set_xticks(angles)
        ax.set_xticklabels(labels, color=TEXT_COLOR, fontsize=9)
        ax.set_ylim(0, 100)
        ax.set_yticks([20, 40, 60, 80, 100])
        ax.set_yticklabels(["20", "40", "60", "80", "100"], color=TEXT_COLOR, fontsize=7)
        ax.yaxis.grid(True, color=GRID_COLOR, alpha=0.6)
        ax.xaxis.grid(True, color=GRID_COLOR, alpha=0.6)
        ax.spines["polar"].set_color(GRID_COLOR)

        ax.set_title(
            "Signal Source Accuracy",
            color=TEXT_COLOR,
            fontsize=11,
            fontweight="bold",
            pad=20,
        )

        return _fig_to_base64(fig)

    @staticmethod
    def drawdown_chart(equity_history: list[dict]) -> str:
        """Drawdown chart computed from equity curve."""
        if not equity_history or len(equity_history) < 2:
            return ""

        dates = []
        values = []
        for point in equity_history:
            try:
                raw = point.get("recorded_at") or point.get("timestamp", "")
                dt = datetime.fromisoformat(str(raw))
                dates.append(dt)
                eq = point.get("total_equity") or point.get("equity", 0)
                values.append(float(eq))
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
        _apply_light_theme(fig, ax)

        ax.fill_between(dates, drawdown_pct, 0, color=RED, alpha=0.3)
        ax.plot(dates, drawdown_pct, color=RED, linewidth=1)
        ax.axhline(y=0, color=TEXT_COLOR, linewidth=0.5, alpha=0.3)
        ax.set_ylabel("Drawdown (%)", color=TEXT_COLOR, fontsize=9)
        ax.set_title("Portfolio Drawdown", color=TEXT_COLOR, fontsize=11, fontweight="bold")
        fig.autofmt_xdate()

        return _fig_to_base64(fig)

    @staticmethod
    def sentiment_trend(sentiment_data: list[dict]) -> str:
        """Bar chart of daily sentiment scores with conviction overlay.

        Args:
            sentiment_data: list of {"date": "YYYY-MM-DD", "signal": float, "conviction": float,
                                     "label": str, "article_count": int}
        """
        if not sentiment_data or len(sentiment_data) < 2:
            return ""

        dates = []
        signals = []
        convictions = []
        for entry in sentiment_data:
            try:
                dates.append(str(entry["date"]))
                signals.append(float(entry.get("signal", 0)))
                convictions.append(float(entry.get("conviction", 0)))
            except (KeyError, ValueError, TypeError):
                continue

        if len(dates) < 2:
            return ""

        fig, ax1 = plt.subplots(figsize=(10, 3))
        _apply_light_theme(fig, ax1)

        colors = [GREEN if s >= 0 else RED for s in signals]
        x = range(len(dates))
        ax1.bar(x, signals, color=colors, width=0.7, alpha=0.8, edgecolor="white", linewidth=0.3)
        ax1.axhline(y=0, color=TEXT_COLOR, linewidth=0.5, alpha=0.3)
        ax1.set_ylabel("Sentiment Score", color=TEXT_COLOR, fontsize=9)
        ax1.set_ylim(-1, 1)

        # Conviction overlay
        ax2 = ax1.twinx()
        ax2.plot(x, convictions, color=ORANGE, linewidth=1.5, marker="o", markersize=3, alpha=0.7)
        ax2.set_ylabel("Conviction", color=ORANGE, fontsize=9)
        ax2.set_ylim(0, 1)
        ax2.tick_params(axis="y", colors=ORANGE, labelsize=8)
        ax2.spines["right"].set_color(ORANGE)

        step = max(1, len(dates) // 12)
        ax1.set_xticks([i for i in x if i % step == 0])
        ax1.set_xticklabels(
            [dates[i] for i in range(len(dates)) if i % step == 0],
            rotation=45, ha="right", fontsize=7,
        )
        ax1.set_title("News Sentiment Trend", color=TEXT_COLOR, fontsize=11, fontweight="bold")

        return _fig_to_base64(fig)

    @staticmethod
    def team_assessment_summary(assessments: dict[str, dict]) -> str:
        """Horizontal bar chart showing each specialist's confidence/health rating.

        Args:
            assessments: dict mapping specialist to {"health_score": int, ...}
        """
        if not assessments:
            return ""

        specialists = []
        scores = []
        colors = []
        for name, data in assessments.items():
            try:
                score = float(data.get("health_score", 50))
                specialists.append(name.replace("_", " ").title())
                scores.append(score)
                colors.append(SPECIALIST_COLORS.get(name, ACCENT))
            except (ValueError, TypeError):
                continue

        if not specialists:
            return ""

        fig, ax = plt.subplots(figsize=(8, 3))
        _apply_light_theme(fig, ax)

        y_pos = range(len(specialists))
        bars = ax.barh(y_pos, scores, color=colors, height=0.6, edgecolor="white", linewidth=0.3)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(specialists, fontsize=9)
        ax.set_xlim(0, 100)
        ax.set_xlabel("Health Score", fontsize=9)
        ax.set_title("Team Assessment Scores", color=TEXT_COLOR, fontsize=11, fontweight="bold")

        # Add value labels
        for bar, score in zip(bars, scores, strict=False):
            color = GREEN if score >= 70 else (ORANGE if score >= 50 else RED)
            ax.text(
                bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                f"{score:.0f}%",
                va="center", fontsize=8, color=color, fontweight="bold",
            )

        ax.invert_yaxis()
        return _fig_to_base64(fig)

    @staticmethod
    def weight_comparison(weights: dict) -> str:
        """Grouped bar chart comparing current vs recommended signal weights.

        Args:
            weights: {"current_weights": {source: w, ...}, "recommended_weights": {source: w, ...}}
        """
        current = weights.get("current_weights", {})
        recommended = weights.get("recommended_weights", {})
        if not current:
            return ""

        sources = list(current.keys())
        current_vals = [float(current.get(s, 0)) for s in sources]
        recommended_vals = [float(recommended.get(s, current.get(s, 0))) for s in sources]

        if not sources:
            return ""

        fig, ax = plt.subplots(figsize=(8, 3))
        _apply_light_theme(fig, ax)

        x = np.arange(len(sources))
        width = 0.35

        ax.bar(
            x - width / 2, current_vals, width,
            label="Current", color=ACCENT, edgecolor="white", linewidth=0.3,
        )
        ax.bar(
            x + width / 2, recommended_vals, width,
            label="Recommended", color=GREEN, edgecolor="white", linewidth=0.3,
        )

        ax.set_xticks(x)
        labels = [s.replace("_", " ").title() for s in sources]
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("Weight", fontsize=9)
        ax.set_title(
            "Signal Weights: Current vs Recommended",
            color=TEXT_COLOR, fontsize=11, fontweight="bold",
        )
        ax.legend(fontsize=8, loc="upper right")

        return _fig_to_base64(fig)
