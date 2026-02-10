# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

crypto-investor — Full-stack crypto investment platform with portfolio tracking, market analysis, automated trading, and a web dashboard. Integrates multiple trading frameworks in a multi-tier architecture.

## Tech Stack

- **Backend**: Python 3.10, FastAPI, SQLAlchemy 2.0 (async), SQLite (aiosqlite), ccxt
- **Frontend**: TypeScript, React 19, Vite 6, TanStack React Query, Tailwind CSS v4, lightweight-charts
- **Tooling**: Makefile-driven, ruff + mypy (Python), eslint (TS), pytest + vitest
- **Trading Frameworks**: Freqtrade (crypto engine), NautilusTrader (multi-asset), VectorBT (research), hftbacktest (HFT)

## Architecture

- **Monorepo**: `backend/` + `frontend/` (web app) alongside platform modules (`common/`, `research/`, `nautilus/`, `freqtrade/`)
- **Database**: SQLite with WAL mode — single-user, low-memory target (Jetson 8GB RAM)
- **Async-first**: FastAPI + ccxt async_support, single uvicorn worker
- **Service layer**: Exchange service wraps ccxt; portfolio/market/trading services depend on it
- **Frontend served by backend in prod** — no Node process needed
- **Multi-tier trading**: VectorBT (screening) → Freqtrade (crypto trading) → NautilusTrader (multi-asset) → hftbacktest (HFT)
- **Shared data pipeline**: Parquet format for OHLCV data shared across all framework tiers

## Commands

```bash
make setup    # Create venv, install deps, init DB, npm install
make dev      # Backend :8000 + frontend :5173 (Vite proxies API)
make test     # pytest + vitest
make lint     # ruff check + eslint
make build    # Production build

# Platform orchestrator
python run.py status                  # Show platform status
python run.py validate                # Validate framework installs
python run.py data generate-sample    # Generate synthetic test data
python run.py data download           # Download real market data
python run.py research screen         # Run VectorBT strategy screens
python run.py freqtrade backtest      # Run Freqtrade backtests
python run.py nautilus test           # Test NautilusTrader engine
```

## Key Paths

- Backend source: `backend/src/app/`
- Backend tests: `backend/tests/`
- Frontend source: `frontend/src/`
- Database files: `backend/data/` (gitignored)
- Alembic migrations: `backend/alembic/`
- Shared data pipeline: `common/data_pipeline/pipeline.py`
- Technical indicators: `common/indicators/technical.py`
- Risk management: `common/risk/risk_manager.py`
- VectorBT screener: `research/scripts/vbt_screener.py`
- NautilusTrader runner: `nautilus/nautilus_runner.py`
- Freqtrade strategies: `freqtrade/user_data/strategies/`
- Freqtrade config: `freqtrade/config.json`
- Platform config: `configs/platform_config.yaml`
- Market data: `data/processed/` (Parquet, gitignored)
- Platform orchestrator: `run.py`

## Conventions

- Python: ruff formatting, type hints everywhere, async def for IO
- TypeScript: strict mode, named exports, functional components
- API routes: `/api/` prefix, RESTful
- Models: SQLAlchemy 2.0 mapped_column style
- Schemas: Pydantic v2 model_validator style
- Platform imports use `common.`, `research.`, `nautilus.` prefixes (PROJECT_ROOT on sys.path)
