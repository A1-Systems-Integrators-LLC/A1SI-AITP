# crypto-investor

Full-stack crypto investment platform with portfolio tracking, market analysis, automated trading, and a web dashboard.

Built for the NVIDIA Jetson Orin Nano — lean on memory, async-first.

## Tech Stack

- **Backend**: Python 3.10, FastAPI, SQLAlchemy 2.0 (async), SQLite, ccxt
- **Frontend**: TypeScript, React 19, Vite, TanStack React Query, Tailwind CSS, lightweight-charts
- **Tooling**: Makefile, ruff, mypy, eslint, pytest, vitest

## Quick Start

```bash
make setup   # Create venv, install deps, init DB, npm install
make dev     # Start backend (:8000) + frontend (:5173)
```

## Commands

| Command       | Description                              |
|---------------|------------------------------------------|
| `make setup`  | Install all dependencies                 |
| `make dev`    | Run backend + frontend in dev mode       |
| `make test`   | Run pytest + vitest                      |
| `make lint`   | Run ruff + eslint                        |
| `make build`  | Production build (frontend + static)     |
| `make clean`  | Remove build artifacts and caches        |

## Project Structure

```
backend/    Python FastAPI backend
frontend/   React TypeScript frontend
scripts/    Dev and setup scripts
```
