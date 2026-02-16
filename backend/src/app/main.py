import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.config import settings
from app.database import async_session, engine
from app.models import Base
from app.routers import (
    backtest,
    data_pipeline,
    exchanges,
    indicators,
    jobs,
    market,
    paper_trading,
    platform,
    portfolio,
    regime,
    risk,
    screening,
    trading,
)

logger = logging.getLogger(__name__)


async def _daily_reset_loop() -> None:
    """Background task: reset daily risk tracking at 00:00 UTC."""
    while True:
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        wait_seconds = (tomorrow - now).total_seconds()
        logger.info(
            f"Daily reset scheduled in {wait_seconds:.0f}s (next: {tomorrow.isoformat()})"
        )
        await asyncio.sleep(wait_seconds)
        try:
            from app.models.risk import RiskState
            from app.services.risk import RiskManagementService

            async with async_session() as session:
                result = await session.execute(select(RiskState))
                states = result.scalars().all()
                service = RiskManagementService(session)
                for state in states:
                    await service.reset_daily(state.portfolio_id)
                logger.info(f"Daily reset completed for {len(states)} portfolio(s)")
        except Exception as e:
            logger.error(f"Daily reset failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Ensure data directory exists
    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create tables (use alembic for migrations in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Enable WAL mode for SQLite
    async with engine.begin() as conn:
        await conn.execute(  # type: ignore[arg-type]
            __import__("sqlalchemy").text("PRAGMA journal_mode=WAL")
        )

    # Start daily risk reset scheduler
    reset_task = asyncio.create_task(_daily_reset_loop())

    yield

    # Cancel daily reset scheduler
    reset_task.cancel()

    # Cleanup: stop paper trading if running
    from app.deps import _paper_trading_service

    if _paper_trading_service is not None and _paper_trading_service.is_running:
        _paper_trading_service.stop()

    await engine.dispose()


app = FastAPI(
    title="crypto-investor",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for dev (Vite at :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(exchanges.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(trading.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(data_pipeline.router, prefix="/api")
app.include_router(screening.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")
app.include_router(indicators.router, prefix="/api")
app.include_router(paper_trading.router, prefix="/api")
app.include_router(regime.router, prefix="/api")
app.include_router(platform.router, prefix="/api")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Serve frontend static files in production (must be last — catch-all mount)
frontend_dist = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
