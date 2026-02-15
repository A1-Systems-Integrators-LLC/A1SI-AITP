"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # portfolios
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("exchange_id", sa.String(50), server_default="binance"),
        sa.Column("description", sa.String(500), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # holdings
    op.create_table(
        "holdings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("amount", sa.Float(), server_default="0.0"),
        sa.Column("avg_buy_price", sa.Float(), server_default="0.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # orders
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exchange_id", sa.String(50), nullable=False),
        sa.Column("exchange_order_id", sa.String(100), server_default=""),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), server_default="0.0"),
        sa.Column("filled", sa.Float(), server_default="0.0"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # risk_states
    op.create_table(
        "risk_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(), nullable=False, unique=True, index=True),
        sa.Column("total_equity", sa.Float(), server_default="10000.0"),
        sa.Column("peak_equity", sa.Float(), server_default="10000.0"),
        sa.Column("daily_start_equity", sa.Float(), server_default="10000.0"),
        sa.Column("daily_pnl", sa.Float(), server_default="0.0"),
        sa.Column("total_pnl", sa.Float(), server_default="0.0"),
        sa.Column("open_positions", sa.JSON(), nullable=True),
        sa.Column("is_halted", sa.Boolean(), server_default="0"),
        sa.Column("halt_reason", sa.String(200), server_default=""),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # risk_limits
    op.create_table(
        "risk_limits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(), nullable=False, unique=True, index=True),
        sa.Column("max_portfolio_drawdown", sa.Float(), server_default="0.15"),
        sa.Column("max_single_trade_risk", sa.Float(), server_default="0.02"),
        sa.Column("max_daily_loss", sa.Float(), server_default="0.05"),
        sa.Column("max_open_positions", sa.Integer(), server_default="10"),
        sa.Column("max_position_size_pct", sa.Float(), server_default="0.20"),
        sa.Column("max_correlation", sa.Float(), server_default="0.70"),
        sa.Column("min_risk_reward", sa.Float(), server_default="1.5"),
        sa.Column("max_leverage", sa.Float(), server_default="1.0"),
    )

    # background_jobs
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(20), server_default="pending", index=True),
        sa.Column("progress", sa.Float(), server_default="0.0"),
        sa.Column("progress_message", sa.String(200), server_default=""),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # backtest_results
    op.create_table(
        "backtest_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("background_jobs.id"),
            index=True,
        ),
        sa.Column("framework", sa.String(20), nullable=False),
        sa.Column("strategy_name", sa.String(100), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("timerange", sa.String(50), server_default=""),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("trades", sa.JSON(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # screen_results
    op.create_table(
        "screen_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("background_jobs.id"),
            index=True,
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("strategy_name", sa.String(50), nullable=False),
        sa.Column("top_results", sa.JSON(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("total_combinations", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # market_data
    op.create_table(
        "market_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("exchange_id", sa.String(50), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("volume_24h", sa.Float(), server_default="0.0"),
        sa.Column("change_24h", sa.Float(), server_default="0.0"),
        sa.Column("high_24h", sa.Float(), server_default="0.0"),
        sa.Column("low_24h", sa.Float(), server_default="0.0"),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # strategies
    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("enabled", sa.Boolean(), server_default="0"),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("strategies")
    op.drop_table("market_data")
    op.drop_table("screen_results")
    op.drop_table("backtest_results")
    op.drop_table("background_jobs")
    op.drop_table("risk_limits")
    op.drop_table("risk_states")
    op.drop_table("orders")
    op.drop_table("holdings")
    op.drop_table("portfolios")
