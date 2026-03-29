# Platform Setup & Deployment

This document covers how to set up the A1SI-AITP platform for local development, run it in Docker containers, configure it for production, and maintain it with backups, TLS, and monitoring.

---

## Prerequisites

### Hardware

The platform is designed for local desktop deployment (MacBook Pro M2 (Apple Silicon)) but runs on any macOS or Linux system.

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 4 cores | 8+ cores (Apple M2) |
| RAM | 4 GB | 16+ GB |
| Storage | 5 GB free | 20+ GB free |
| GPU | Not required | Optional (for future PyTorch/ML) |

### Software

| Dependency | Version | Notes |
|-----------|---------|-------|
| Python | 3.10+ | System python3 or pyenv |
| Node.js | 20+ | Via nvm recommended |
| npm | 9+ | Comes with Node |
| Git | 2.x | For version control |
| SQLite3 | 3.37+ | Usually pre-installed |
| Docker | 24+ | For containerized deployment (required — all code runs in Docker) |
| OpenSSL | 1.1+ | For TLS certificate generation |

**Note:** This platform targets macOS (Apple Silicon). Docker images are built for `linux/arm64` by default; `linux/amd64` builds are also supported.

---

## Quick Start

```bash
# Clone the repository
git clone git@github.com:rredmer/A1SI-AITP.git
cd A1SI-AITP

# Generate secrets and create .env
bash scripts/generate_secrets.sh

# Run full setup (backend venv + deps + DB + frontend npm install)
make setup

# Start development servers
make dev
```

This gives you:
- Backend API at http://localhost:8000
- Frontend dashboard at http://localhost:5173
- Django admin at http://localhost:8000/admin/
- Default login: `admin` / `admin`

---

## Detailed Setup

### 1. Generate Secrets

The `generate_secrets.sh` script creates all required cryptographic keys and writes them to `.env`:

```bash
bash scripts/generate_secrets.sh
```

This generates:
- `DJANGO_SECRET_KEY` — Django session signing key
- `DJANGO_ENCRYPTION_KEY` — Fernet key for encrypting exchange API credentials at rest
- `FREQTRADE__API_SERVER__JWT_SECRET_KEY` — JWT signing for Freqtrade API
- `FREQTRADE__API_SERVER__PASSWORD` — Freqtrade API password
- `BACKUP_ENCRYPTION_KEY` — GPG passphrase for encrypted database backups

The script sets `.env` permissions to 600 (owner read/write only). If `.env` already exists, it replaces only the secret keys, preserving other settings.

To generate secrets manually:

```bash
# Django secret key
python3 -c "import secrets; print(secrets.token_urlsafe(50))"

# Fernet encryption key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Configure Environment

Edit `.env` to add exchange API keys and notification settings. See `.env.example` for all available options.

```bash
# ── Django ────
DJANGO_SECRET_KEY=<generated>
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# ── Encryption ────
DJANGO_ENCRYPTION_KEY=<generated>

# ── CORS ────
CORS_ALLOWED_ORIGINS=http://localhost:5173

# ── Exchange API keys (optional, can also configure via web UI) ────
EXCHANGE_ID=kraken
BINANCE_API_KEY=
BINANCE_SECRET=

# ── Notifications (optional) ────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ── Freqtrade ────
FREQTRADE__API_SERVER__JWT_SECRET_KEY=<generated>
FREQTRADE__API_SERVER__PASSWORD=<generated>

# ── Backups ────
BACKUP_ENCRYPTION_KEY=<generated>

# ── Platform ────
LOG_LEVEL=INFO
DRY_RUN=true
```

### 3. Backend Setup

```bash
make setup-backend
```

This runs the following steps:

1. **Create Python virtual environment** at `backend/.venv/`
   - Uses `--without-pip` if system python3 has no `ensurepip`
   - Bootstraps pip via `get-pip.py` if needed
2. **Install Python dependencies** from `backend/pyproject.toml` (editable install with dev extras)
3. **Create data directory** at `backend/data/`
4. **Run database migrations** (creates SQLite database at `backend/data/a1si_aitp.db`)
5. **Create admin superuser** (`admin`/`admin`) or re-hash existing password with Argon2id

### Python Dependencies

Core backend dependencies (`backend/pyproject.toml`):

| Package | Version | Purpose |
|---------|---------|---------|
| Django | 5.1+ | Web framework |
| djangorestframework | 3.15+ | REST API |
| channels + daphne | 4+ | ASGI server + WebSocket support |
| ccxt | 4+ | Exchange connectivity (200+ exchanges) |
| cryptography | 44+ | Fernet encryption for API keys |
| argon2-cffi | 23+ | Argon2id password hashing |
| httpx | 0.27+ | HTTP client for notifications |
| python-dotenv | 1+ | Environment variable loading |

Dev dependencies: pytest, pytest-django, ruff, mypy, pip-audit.

Analysis extras (for risk VaR calculations): pandas, numpy, scipy.

### 4. Frontend Setup

```bash
make setup-frontend
```

Runs `npm install` in the `frontend/` directory.

Frontend tech stack:

| Package | Version | Purpose |
|---------|---------|---------|
| React | 19 | UI framework |
| TypeScript | 5.9 | Type safety |
| Vite | 7 | Dev server + bundler |
| TanStack React Query | 5 | Server state management |
| Tailwind CSS | 4 | Styling |
| lightweight-charts | 5 | Candlestick charts |
| react-router-dom | 7 | Client-side routing |

---

## Development

### Starting Dev Servers

```bash
make dev
```

This runs `scripts/dev.sh`, which starts both servers in parallel with a cleanup trap:

- **Backend:** Daphne ASGI server on port 8000
  ```
  cd backend && .venv/bin/python -m daphne -b 0.0.0.0 -p 8000 config.asgi:application
  ```
- **Frontend:** Vite dev server on port 5173
  ```
  cd frontend && npm run dev
  ```

Press `Ctrl+C` to shut down both servers cleanly.

You can also start them individually:

```bash
make dev-backend     # Backend only (port 8000)
make dev-frontend    # Frontend only (port 5173)
```

### API Proxy

In development, the Vite dev server proxies `/api/*` requests to the backend:

```typescript
// frontend/vite.config.ts
server: {
  proxy: {
    "/api": {
      target: "http://localhost:8000",
      changeOrigin: true,
    },
  },
},
```

This means the frontend at `http://localhost:5173` can call `http://localhost:5173/api/health/` and it transparently reaches the Django backend on port 8000.

### Database Operations

```bash
make migrate          # Run makemigrations + migrate
make createsuperuser  # Create a new superuser interactively
```

The SQLite database is stored at `backend/data/a1si_aitp.db` with DELETE journal mode (required for Docker virtiofs compatibility).

### Testing

```bash
make test             # Run all tests (backend + frontend)
make test-backend     # Backend only (pytest)
make test-frontend    # Frontend only (vitest)
make test-security    # Auth + security tests only
```

Backend tests live in `backend/tests/`. Frontend tests live in `frontend/tests/`.

### Linting

```bash
make lint             # All linting (backend + frontend)
make lint-backend     # ruff check (Python)
make lint-frontend    # eslint (TypeScript)
```

Ruff enforces import sorting (isort rules). Migrations are excluded from linting.

### Building

```bash
make build            # Production frontend build → frontend/dist/
```

---

## Docker Deployment

Docker Compose runs the platform as two containers: backend (Daphne) and frontend (nginx). Two environments are available: **dev** (docker-compose.yml) and **prod** (docker-compose.prod.yml).

### Architecture

```
                    ┌─────────────────┐
                    │   User Browser   │
                    └────────┬────────┘
                             │
               Dev :4001 / Prod :4101
                             ▼
                    ┌─────────────────┐
                    │    Frontend      │
                    │    (nginx)       │
                    │                  │
                    │  Static files    │
                    │  SPA routing     │
                    │  /api/ proxy ────┼──────┐
                    └─────────────────┘      │
                                             │ Dev :4000 / Prod :4100
                                             ▼
                    ┌─────────────────┐
                    │    Backend       │
                    │    (Daphne)      │
                    │                  │
                    │  Django + DRF    │
                    │  ASGI/Channels   │
                    │  SQLite (volume) │
                    └─────────────────┘
```

### Building and Running

**Dev environment** (default):

```bash
# Build and start both containers in background
docker compose up --build -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

**Prod environment:**

```bash
# Build and start prod containers in background
docker compose -f docker-compose.prod.yml up --build -d

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Stop
docker compose -f docker-compose.prod.yml down
```

### Dev vs Prod

| Aspect                       | Dev                | Prod                    |
|------------------------------|--------------------|-------------------------|
| Compose file                 | docker-compose.yml | docker-compose.prod.yml |
| Backend port                 | 4000               | 4100                    |
| Frontend port                | 4001               | 4101                    |
| `DJANGO_DEBUG`               | true               | false                   |
| Secrets                      | Dev fallbacks      | Required (enforced)     |
| Both can run simultaneously  | Yes                | Yes                     |

The dev and prod environments use separate containers and volumes, so they can run side by side without conflict. Use dev for daily development and testing; use prod for staging or deployment verification.

### Access URLs

**Dev:**
- Frontend: http://localhost:4001
- Backend API: http://localhost:4000
- Default login: `admin` / `admin`

**Prod:**
- Frontend: http://localhost:4101
- Backend API: http://localhost:4100
- Default login: `admin` / `admin` (change immediately)

### Backend Container

**Dockerfile:** `backend/Dockerfile`

```dockerfile
FROM python:3.12-slim
# Installs gcc, libffi-dev for cryptography/argon2
# pip install -e . (from pyproject.toml)
# Entrypoint: docker-entrypoint.sh → Daphne on port 8000
```

**Entrypoint** (`backend/docker-entrypoint.sh`):
1. Runs `migrate --run-syncdb` on startup
2. Creates admin superuser if it doesn't exist
3. Starts Daphne ASGI server

**Health check:** `curl -f http://localhost:8000/api/health/` every 15 seconds.

**Data volume:** Bind mount `./backend/data` mounted at `/project/backend/data` — persists the SQLite database across container restarts.

### Frontend Container

**Dockerfile:** `frontend/Dockerfile`

Multi-stage build:
1. **Build stage:** `node:20-alpine` — runs `npm ci && npm run build`
2. **Serve stage:** `nginx:alpine` — serves static files from the build output

**nginx config** (`frontend/nginx.conf`):
- Serves `frontend/dist/` as static files
- SPA routing: all paths fall through to `index.html`
- Proxies `/api/*` to the `backend` container on port 8000
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy`

### Environment Variables

Pass exchange credentials and settings via environment or `.env`:

```bash
# Use .env file (docker compose reads it automatically)
cp .env.example .env
# Edit .env with your values

# Or pass inline
EXCHANGE_ID=kraken EXCHANGE_API_KEY=xxx docker compose up
```

Key variables for Docker:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DJANGO_SECRET_KEY` | docker dev key | Session signing (change in prod) |
| `DJANGO_DEBUG` | true | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | localhost,127.0.0.1,backend | Allowed Host header values |
| `DJANGO_ENCRYPTION_KEY` | dev fallback | Fernet key for credential encryption |
| `CORS_ALLOWED_ORIGINS` | localhost:4001,localhost:5173 | Allowed CORS origins |
| `CSRF_TRUSTED_ORIGINS` | localhost:4001,localhost:5173,localhost:4000 | Trusted CSRF origins |
| `EXCHANGE_ID` | binance | Default exchange |
| `EXCHANGE_API_KEY` | (empty) | Fallback API key |
| `EXCHANGE_API_SECRET` | (empty) | Fallback API secret |

---

## Port Allocation

All A1SI-AITP services use the 4000-4199 port range:

| Service                      | Dev/Test | Prod | Notes               |
|------------------------------|----------|------|---------------------|
| Backend (Django/Daphne)      | 4000     | 4100 | API + Admin         |
| Frontend (nginx)             | 4001     | 4101 | SPA + API proxy     |
| Prometheus                   | 4010     | 4110 | monitoring profile  |
| Grafana                      | 4011     | 4111 | monitoring profile  |
| PostgreSQL                   | 4012     | 4112 | postgres profile    |
| Freqtrade CIV1               | 4080     | 4180 | Bare-metal only     |
| Freqtrade BMR                | 4083     | 4183 | Bare-metal only     |
| Freqtrade VB                 | 4084     | 4184 | Bare-metal only     |
| Freqtrade Short              | 4085     | 4185 | Future              |
| Freqtrade Grid               | 4086     | 4186 | Future              |
| Freqtrade Scalp              | 4087     | 4187 | Future              |
| Freqtrade Sentiment          | 4088     | 4188 | Future              |
| Freqtrade Reversal           | 4089     | 4189 | Future              |
| Vite dev server              | 5173     | ---  | Local dev only      |

The 4000-4199 range is exclusive to A1SI-AITP. Other A1SI projects use different ranges to ensure zero port conflicts when running Docker stacks simultaneously.

---

## Production Deployment

### Security Checklist

Before deploying to production:

- [ ] Generate unique secrets: `bash scripts/generate_secrets.sh`
- [ ] Set `DJANGO_DEBUG=false`
- [ ] Set a strong `DJANGO_SECRET_KEY` (not the default)
- [ ] Set `DJANGO_ENCRYPTION_KEY` (required when DEBUG=false)
- [ ] Change the default admin password
- [ ] Set `DJANGO_ALLOWED_HOSTS` to your domain
- [ ] Set `CSRF_TRUSTED_ORIGINS` to your domain with scheme
- [ ] Set `CORS_ALLOWED_ORIGINS` to your frontend domain
- [ ] Generate TLS certificates: `make certs`
- [ ] Run `make harden` to set file permissions
- [ ] Run `make audit` to check for dependency vulnerabilities
- [ ] Configure `BACKUP_ENCRYPTION_KEY` for encrypted backups
- [ ] Set up a backup cron job

### Django Production Settings

When `DJANGO_DEBUG=false`, the following security features activate automatically:

| Setting | Value | Purpose |
|---------|-------|---------|
| `SECRET_KEY` | Required (non-default) | Enforced — raises ValueError if not set |
| `ENCRYPTION_KEY` | Required | Enforced — raises ValueError if not set |
| `SESSION_COOKIE_SECURE` | True | Cookies only sent over HTTPS |
| `CSRF_COOKIE_SECURE` | True | CSRF cookie only sent over HTTPS |
| `SECURE_HSTS_SECONDS` | 31536000 (1 year) | HTTP Strict Transport Security |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | True | HSTS applies to subdomains |
| `SECURE_HSTS_PRELOAD` | True | Eligible for browser HSTS preload list |
| `SECURE_SSL_REDIRECT` | Configurable | Redirect HTTP to HTTPS |

Additional security features always active:

| Feature | Implementation |
|---------|---------------|
| Password hashing | Argon2id (primary), PBKDF2 (fallback) |
| Minimum password length | 12 characters |
| Rate limiting | 120 req/min general, 20 req/min login |
| Login lockout | 5 failed attempts → 30 minute lockout |
| Security logging | Rotating file at `backend/data/logs/security.log` (10 MB, 10 backups) |
| Audit middleware | Logs security-relevant requests |
| X-Frame-Options | DENY |
| X-Content-Type-Options | nosniff |
| XSS filter | Enabled |

### TLS Certificates

Generate self-signed certificates for development/internal use:

```bash
make certs
```

This runs `scripts/generate_certs.sh`, which:
1. Creates `backend/certs/` directory
2. Generates a 2048-bit RSA key and self-signed X.509 certificate (365 days)
3. Includes SANs for hostname, localhost, and 127.0.0.1
4. Sets key file to mode 600

To run Daphne with TLS:

```bash
cd backend && .venv/bin/python -m daphne \
    -e ssl:8443:privateKey=certs/server.key:certKey=certs/server.crt \
    config.asgi:application
```

For production, use certificates from Let's Encrypt or your CA instead.

### File Permission Hardening

```bash
make harden
```

This sets:

| Path | Permission | Purpose |
|------|-----------|---------|
| `.env` | 600 | Only owner can read secrets |
| `backend/data/` | 770 | Database directory |
| `backend/data/logs/` | 770 | Log directory |
| `backend/certs/` | 700 | TLS certificate directory |

It also verifies that critical environment variables are set.

### Dependency Auditing

```bash
make audit
```

Runs:
1. `pip-audit` — checks Python packages against known vulnerabilities
2. `npm audit --omit=dev` — checks production npm packages

---

## Database Backups

### Running a Backup

```bash
make backup
```

This runs `scripts/backup_db.sh`, which:

1. Creates a SQLite `.backup` of `backend/data/a1si_aitp.db`
2. Compresses with gzip
3. If `BACKUP_ENCRYPTION_KEY` is set:
   - Encrypts with GPG symmetric AES-256
   - Generates a SHA-256 checksum file
   - Removes the unencrypted compressed file
4. Retains the 7 most recent backups (auto-deletes older ones)

Output location: `backend/data/backups/`

File naming: `a1si_aitp_{TIMESTAMP}.db.gz.gpg` (encrypted) or `a1si_aitp_{TIMESTAMP}.db.gz` (unencrypted)

### Restoring from Backup

```bash
make restore
```

This runs `scripts/restore_db.sh`, which:

1. Auto-selects the most recent backup file (or specify one: `bash scripts/restore_db.sh path/to/backup.db.gz.gpg`)
2. Verifies the SHA-256 checksum (if `.sha256` file exists)
3. Decrypts with GPG if `.gpg` (requires `BACKUP_ENCRYPTION_KEY`)
4. Decompresses with gunzip
5. Runs `PRAGMA integrity_check` on the restored database
6. Saves the current database as `.pre-restore` safety net
7. Copies the verified backup into place

After restoring, run `make migrate` to apply any pending migrations.

To restore a specific backup file:

```bash
bash scripts/restore_db.sh backend/data/backups/a1si_aitp_20260218_120000.db.gz.gpg
```

### Automated Backups

Add a cron job for daily backups:

```bash
# Edit crontab
crontab -e

# Add line (daily at 2 AM)
0 2 * * * cd /path/to/A1SI-AITP && make backup >> backend/data/logs/backup.log 2>&1
```

---

## Platform Orchestrator

The `run.py` CLI coordinates all framework tiers beyond the web application.

### Status & Validation

```bash
# Show framework status, data files, strategies, config
python run.py status

# Validate all framework imports (CCXT, Freqtrade, VectorBT, Nautilus, etc.)
python run.py validate
```

### Data Pipeline

```bash
# Download market data from exchanges
python run.py data download --symbols BTC/USDT,ETH/USDT --timeframes 1h,4h --exchange binance --days 365

# List available Parquet files
python run.py data list

# Show dataset info
python run.py data info BTC/USDT --timeframe 1h --exchange binance

# Generate synthetic test data (no API keys needed)
python run.py data generate-sample
```

### Research & Trading

```bash
# VectorBT strategy screening
python run.py research screen --symbol BTC/USDT --timeframe 1h --fees 0.001

# Freqtrade backtest
python run.py freqtrade backtest --strategy CryptoInvestorV1

# Freqtrade paper trading
python run.py freqtrade dry-run --strategy CryptoInvestorV1

# Freqtrade parameter optimization
python run.py freqtrade hyperopt --strategy CryptoInvestorV1 --epochs 100

# List strategies
python run.py freqtrade list-strategies

# NautilusTrader engine test
python run.py nautilus test

# Convert data for NautilusTrader
python run.py nautilus convert --symbol BTC/USDT --timeframe 1h
```

---

## Project Structure

```
A1SI-AITP/
├── backend/                     # Django backend
│   ├── config/                  #   Settings, URLs, ASGI config
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── asgi.py
│   ├── core/                    #   Auth, health, middleware, platform bridge
│   ├── portfolio/               #   Portfolio tracking models/views
│   ├── trading/                 #   Order tracking models/views
│   ├── market/                  #   Exchange service, OHLCV, config management
│   ├── risk/                    #   Risk management service + API
│   ├── analysis/                #   Background jobs, backtest results
│   ├── tests/                   #   Backend test suite
│   ├── data/                    #   SQLite DB, logs, backups (gitignored)
│   ├── certs/                   #   TLS certificates (gitignored)
│   ├── Dockerfile
│   ├── docker-entrypoint.sh
│   └── pyproject.toml           #   Python dependencies + tool config
├── frontend/                    # React frontend
│   ├── src/
│   │   ├── api/                 #   API client functions
│   │   ├── components/          #   Reusable UI components
│   │   ├── hooks/               #   Custom React hooks
│   │   ├── pages/               #   Page components (Dashboard, Settings, etc.)
│   │   └── types/               #   TypeScript type definitions
│   ├── tests/                   #   Frontend test suite
│   ├── Dockerfile
│   ├── nginx.conf               #   Production nginx config
│   ├── vite.config.ts
│   └── package.json
├── common/                      # Shared platform modules
│   ├── data_pipeline/           #   OHLCV fetching, storage, validation
│   ├── indicators/              #   Technical indicator library
│   ├── risk/                    #   Risk manager engine
│   └── regime/                  #   Market regime detector + strategy router
├── research/                    # VectorBT research tier
│   └── scripts/vbt_screener.py
├── freqtrade/                   # Freqtrade trading tier
│   ├── config.json
│   └── user_data/strategies/    #   Trading strategies
├── nautilus/                    # NautilusTrader tier
│   └── nautilus_runner.py
├── configs/
│   └── platform_config.yaml     # Master platform configuration
├── scripts/
│   ├── generate_secrets.sh      # Generate all cryptographic keys
│   ├── dev.sh                   # Start dev servers
│   ├── generate_certs.sh        # Generate TLS certificates
│   ├── backup_db.sh             # Database backup with encryption
│   ├── restore_db.sh            # Database restore with integrity check
│   └── setup.sh
├── docs/                        # Documentation
├── data/                        # Market data Parquet files (gitignored)
├── run.py                       # Platform orchestrator CLI
├── Makefile                     # Build/dev/test commands
├── docker-compose.yml           # Container orchestration
├── .env.example                 # Environment variable template
└── .gitignore
```

---

## Make Targets Reference

| Target | Description |
|--------|-------------|
| `make setup` | Full setup: backend venv + deps + DB + frontend npm install |
| `make setup-backend` | Backend only: venv, pip install, migrate, create admin |
| `make setup-frontend` | Frontend only: npm install |
| `make dev` | Start both dev servers (backend :8000, frontend :5173) |
| `make dev-backend` | Start backend only (Daphne on :8000) |
| `make dev-frontend` | Start frontend only (Vite on :5173) |
| `make migrate` | Run Django makemigrations + migrate |
| `make createsuperuser` | Create Django superuser interactively |
| `make test` | Run all tests (pytest + vitest) |
| `make test-backend` | Backend tests only |
| `make test-frontend` | Frontend tests only |
| `make test-security` | Auth and security tests only |
| `make lint` | Run all linters (ruff + eslint) |
| `make lint-backend` | Python linting (ruff) |
| `make lint-frontend` | TypeScript linting (eslint) |
| `make build` | Production frontend build to `frontend/dist/` |
| `make harden` | Set file permissions (600 .env, 770 data dirs) |
| `make audit` | Check dependencies for vulnerabilities |
| `make certs` | Generate self-signed TLS certificates |
| `make backup` | SQLite backup with optional GPG encryption |
| `make restore` | Restore SQLite database from most recent backup |
| `make docker-prod-up` | Start prod containers (backend :4100, frontend :4101) |
| `make docker-prod-down` | Stop prod containers |
| `make docker-prod-deploy` | Full prod deploy: build + restart + verify |
| `make monitoring` | Start dev monitoring (Prometheus :4010, Grafana :4011) |
| `make monitoring-prod` | Start prod monitoring (Prometheus :4110, Grafana :4111) |
| `make clean` | Remove venv, node_modules, build artifacts, caches |

---

## Troubleshooting

### Backend won't start

**"No module named pip"** during setup:
Some system Python installations lack `ensurepip`. The Makefile handles this by creating the venv with `--without-pip` and bootstrapping via `get-pip.py`. If setup still fails, manually bootstrap:

```bash
python3 -m venv --without-pip backend/.venv
curl -sS https://bootstrap.pypa.io/get-pip.py | backend/.venv/bin/python
backend/.venv/bin/pip install -e "backend[dev]"
```

**"DJANGO_SECRET_KEY must be set in production":**
You're running with `DJANGO_DEBUG=false` but haven't set the secret key. Either set `DJANGO_DEBUG=true` for development or set `DJANGO_SECRET_KEY` in `.env`.

**"DJANGO_ENCRYPTION_KEY must be set in production":**
Same as above — set the encryption key or enable debug mode.

### Frontend won't start

**Port 5173 in use:**
Another Vite instance is running. Kill it with `lsof -ti:5173 | xargs kill` or change the port in `vite.config.ts`.

**API calls return 403:**
CSRF token mismatch. Ensure `CSRF_TRUSTED_ORIGINS` includes your frontend URL with the scheme (e.g., `http://localhost:5173`).

### Docker issues

**Backend unhealthy:**
Check logs with `docker compose logs backend`. Common causes:
- Missing environment variables
- Port 8000 already in use on host

**Frontend can't reach backend:**
The nginx config proxies `/api/` to `http://backend:8000`. Ensure the backend container is healthy before the frontend starts (the `depends_on` condition handles this).

**Data not persisting:**
The `backend-data` volume persists the SQLite database. If you ran `docker compose down -v`, the volume was deleted. Use `docker compose down` (without `-v`) to keep data.

### Database

**"database is locked":**
SQLite with DELETE journal mode supports only one writer at a time. If multiple processes write simultaneously, you may see this error. The platform is designed for single-user operation — ensure only one backend instance runs at a time. Note: the database uses DELETE journal mode exclusively. WAL mode is not used — it is incompatible with Docker virtiofs bind mounts and destroyed the production database three times.

**Corrupted database:**
Restore from the most recent backup:
```bash
make restore
# Or specify a backup file:
bash scripts/restore_db.sh backend/data/backups/a1si_aitp_20260218_120000.db.gz.gpg
```
