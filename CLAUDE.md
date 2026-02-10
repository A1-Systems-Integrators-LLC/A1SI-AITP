# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

crypto-investor — Full-stack crypto investment platform with portfolio tracking, market analysis, automated trading, and a web dashboard.

## Tech Stack

- **Backend**: Python 3.10, FastAPI, SQLAlchemy 2.0 (async), SQLite (aiosqlite), ccxt
- **Frontend**: TypeScript, React 19, Vite 6, TanStack React Query, Tailwind CSS v4, lightweight-charts
- **Tooling**: Makefile-driven, ruff + mypy (Python), eslint (TS), pytest + vitest

## Architecture

- **Monorepo**: `backend/` and `frontend/` at top level
- **Database**: SQLite with WAL mode — single-user, low-memory target (Jetson 8GB RAM)
- **Async-first**: FastAPI + ccxt async_support, single uvicorn worker
- **Service layer**: Exchange service wraps ccxt; portfolio/market/trading services depend on it
- **Frontend served by backend in prod** — no Node process needed

## Commands

```bash
make setup    # Create venv, install deps, init DB, npm install
make dev      # Backend :8000 + frontend :5173 (Vite proxies API)
make test     # pytest + vitest
make lint     # ruff check + eslint
make build    # Production build
```

## Key Paths

- Backend source: `backend/src/app/`
- Backend tests: `backend/tests/`
- Frontend source: `frontend/src/`
- Database files: `backend/data/` (gitignored)
- Alembic migrations: `backend/alembic/`

## Conventions

- Python: ruff formatting, type hints everywhere, async def for IO
- TypeScript: strict mode, named exports, functional components
- API routes: `/api/` prefix, RESTful
- Models: SQLAlchemy 2.0 mapped_column style
- Schemas: Pydantic v2 model_validator style
