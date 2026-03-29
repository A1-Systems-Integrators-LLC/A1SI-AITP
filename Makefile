.PHONY: setup dev start stop test lint build clean harden audit certs backup restore analyze test-security test-e2e ci typecheck docker-build check-schema-freshness generate-types install-hooks docker-up docker-down docker-restart docker-deploy docker-deploy-clean docker-prod-up docker-prod-down docker-prod-deploy docker-prod-logs docker-logs docker-logs-backend docker-logs-frontend docker-status docker-clean maintain-db health-check clean-data pilot-preflight pilot-preflight-json pilot-status pilot-status-json pilot-status-full smoke-test verify monitoring monitoring-prod watchdog watchdog-fix setup-cron

BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV := $(BACKEND_DIR)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
MANAGE := cd $(BACKEND_DIR) && $(CURDIR)/$(PYTHON) manage.py

# ── Setup ──────────────────────────────────────────────────

setup: setup-backend setup-frontend install-hooks
	@echo "✓ Setup complete"

setup-backend:
	@echo "→ Setting up backend..."
	@if [ ! -d "$(VENV)" ]; then \
		python3 -m venv --without-pip $(VENV) && \
		curl -sS https://bootstrap.pypa.io/get-pip.py | $(PYTHON); \
	fi
	$(PIP) install -e "$(BACKEND_DIR)[dev,trading]" --quiet
	@mkdir -p $(BACKEND_DIR)/data
	$(MANAGE) migrate --run-syncdb
	@echo "→ Creating superuser (if needed) and ensuring Argon2 hash..."
	@$(MANAGE) shell -c "\
from django.contrib.auth.models import User;\
u, created = User.objects.get_or_create(username='admin', defaults={'is_superuser': True, 'is_staff': True});\
if created: u.set_password('admin'); u.save(); print('Created admin user')\
elif not u.password.startswith('argon2'): u.set_password('admin'); u.save(); print('Re-hashed admin password with Argon2')\
else: print('Admin user OK')" 2>/dev/null || true

setup-frontend:
	@echo "→ Setting up frontend..."
	cd $(FRONTEND_DIR) && npm install --silent

# ── Development ────────────────────────────────────────────

dev:
	@bash scripts/dev.sh

start:
	@bash scripts/start.sh

start-all:
	FREQTRADE_INSTANCES=CryptoInvestorV1,BollingerMeanReversion,VolatilityBreakout,MomentumShort,GridDCA,MomentumScalper15m,SentimentEventTrader,TrendReversal $(MAKE) start

stop:
	@bash scripts/stop.sh

dev-backend:
	cd $(BACKEND_DIR) && $(CURDIR)/$(PYTHON) -m daphne -b 0.0.0.0 -p 8000 config.asgi:application

dev-frontend:
	cd $(FRONTEND_DIR) && npm run dev

# ── Database ──────────────────────────────────────────────

migrate:
	$(MANAGE) makemigrations
	$(MANAGE) migrate

createsuperuser:
	$(MANAGE) createsuperuser

# ── Testing ────────────────────────────────────────────────

test: test-backend test-frontend
	@echo "✓ All tests passed"

test-backend:
	cd $(BACKEND_DIR) && $(CURDIR)/$(PYTHON) -m pytest tests/ -v

test-frontend:
	cd $(FRONTEND_DIR) && npx vitest run

test-security:
	cd $(BACKEND_DIR) && $(CURDIR)/$(PYTHON) -m pytest tests/test_auth.py tests/test_security.py -v

test-docker: test-docker-backend test-docker-frontend
	@echo "✓ All Docker tests passed"

test-docker-backend:
	docker compose exec backend python -m pytest tests/ -v

test-docker-frontend:
	cd $(FRONTEND_DIR) && npx vitest run

test-e2e:
	cd $(FRONTEND_DIR) && npx playwright test

# ── Linting ────────────────────────────────────────────────

lint: lint-backend lint-frontend check-schema-freshness
	@echo "✓ All linting passed"

lint-backend:
	$(VENV)/bin/ruff check $(BACKEND_DIR)/core/ $(BACKEND_DIR)/portfolio/ $(BACKEND_DIR)/trading/ $(BACKEND_DIR)/market/ $(BACKEND_DIR)/risk/ $(BACKEND_DIR)/analysis/ $(BACKEND_DIR)/tests/ common/ nautilus/ hftbacktest/ research/

lint-frontend:
	cd $(FRONTEND_DIR) && npx eslint .

# ── Build ──────────────────────────────────────────────────

build: generate-types
	cd $(FRONTEND_DIR) && npm run build
	@echo "✓ Frontend built to $(FRONTEND_DIR)/dist/"

# ── Type checking ─────────────────────────────────────────

typecheck:
	cd $(FRONTEND_DIR) && npx tsc --noEmit -p tsconfig.app.json
	@echo "✓ TypeScript type check passed"

generate-types:
	$(MANAGE) spectacular --file $(CURDIR)/$(FRONTEND_DIR)/schema.yaml
	cd $(FRONTEND_DIR) && npx openapi-typescript schema.yaml -o src/types/api-schema.ts
	@echo "✓ TypeScript API types regenerated"

check-schema-freshness:
	@echo "→ Checking schema freshness..."
	@$(MANAGE) spectacular --file /tmp/schema-check.yaml 2>/dev/null
	@diff -q $(CURDIR)/$(FRONTEND_DIR)/schema.yaml /tmp/schema-check.yaml >/dev/null 2>&1 \
		&& echo "✓ Schema is up to date" \
		|| (echo "✗ Schema is stale — run 'make generate-types' to update" && exit 1)
	@rm -f /tmp/schema-check.yaml

install-hooks:
	@cp scripts/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "✓ Git hooks installed"

# ── Docker (Dev/Test — ports 4000-4099) ───────────────────

docker-build:
	@echo "→ Building Docker images..."
	docker compose build
	@echo "✓ Docker images built"

docker-build-clean:
	@echo "→ Rebuilding Docker images (no cache)..."
	docker compose build --no-cache
	@echo "✓ Docker images rebuilt"

docker-up:
	@echo "→ Starting dev containers (backend :4000, frontend :4001)..."
	docker compose up -d
	@echo "→ Waiting for health checks..."
	@timeout 60 sh -c 'until docker compose ps --format json | grep -q '"'"'"Health":"healthy"'"'"'; do sleep 2; done' 2>/dev/null \
		&& echo "✓ Dev containers healthy" \
		|| (echo "⚠ Health check timeout — check logs with 'make docker-logs'" && docker compose ps)
	@echo ""
	@echo "  Dev environment:"
	@echo "    Frontend:  http://localhost:4001"
	@echo "    Backend:   http://localhost:4000"
	@echo "    API:       http://localhost:4000/api/"
	@echo "    Admin:     http://localhost:4000/admin/"

docker-down:
	@echo "→ Stopping dev containers..."
	docker compose down
	@echo "✓ Dev containers stopped"

docker-restart:
	@echo "→ Restarting dev containers..."
	$(MAKE) docker-down
	$(MAKE) docker-up

docker-deploy:
	@echo "→ Full dev deploy: build + restart + verify..."
	$(MAKE) docker-build
	$(MAKE) docker-down
	$(MAKE) docker-up
	$(MAKE) smoke-test
	@echo "✓ Dev deploy complete"

docker-deploy-clean:
	@echo "→ Full clean dev deploy: rebuild + restart + verify..."
	$(MAKE) docker-build-clean
	$(MAKE) docker-down
	$(MAKE) docker-up
	$(MAKE) smoke-test
	@echo "✓ Clean dev deploy complete"

# ── Docker (Prod — ports 4100-4199) ──────────────────────

docker-prod-up:
	@echo "→ Starting prod containers (backend :4100, frontend :4101)..."
	docker compose --profile prod up -d
	@echo "→ Waiting for health checks..."
	@timeout 60 sh -c 'until docker inspect --format="{{if .State.Health}}{{.State.Health.Status}}{{end}}" aitp-backend-prod 2>/dev/null | grep -q healthy; do sleep 2; done' 2>/dev/null \
		&& echo "✓ Prod containers healthy" \
		|| (echo "⚠ Health check timeout" && docker compose --profile prod ps)
	@echo ""
	@echo "  Prod environment:"
	@echo "    Frontend:  http://localhost:4101"
	@echo "    Backend:   http://localhost:4100"
	@echo "    API:       http://localhost:4100/api/"

docker-prod-down:
	@echo "→ Stopping prod containers..."
	docker compose --profile prod down
	@echo "✓ Prod containers stopped"

docker-prod-deploy:
	@echo "→ Full prod deploy: build + restart + verify..."
	$(MAKE) docker-build
	$(MAKE) docker-prod-down
	$(MAKE) docker-prod-up
	@echo "→ Running prod smoke test..."
	@curl -sf http://localhost:4100/api/health/ | python3 -m json.tool > /dev/null 2>&1 \
		&& echo "✓ Prod smoke test passed" \
		|| echo "✗ Prod smoke test failed"
	@echo "✓ Prod deploy complete"

docker-prod-logs:
	docker compose --profile prod logs -f --tail=50

# ── Docker (shared) ──────────────────────────────────────

docker-logs:
	docker compose logs -f --tail=50

docker-logs-backend:
	docker compose logs -f --tail=50 backend

docker-logs-frontend:
	docker compose logs -f --tail=50 frontend

docker-status:
	@echo "── AITP Container Status ──"
	@docker ps --filter "name=aitp-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "No AITP containers running"

docker-clean:
	@echo "→ Removing all AITP containers, images, and volumes..."
	docker compose --profile prod --profile monitoring --profile postgres --profile prod-monitoring --profile prod-postgres down -v --rmi local 2>/dev/null || true
	docker compose down -v --rmi local 2>/dev/null || true
	@echo "✓ All AITP Docker artifacts cleaned"

# ── CI pipeline (lint + typecheck + test + audit) ─────────

ci: lint typecheck check-schema-freshness test audit
	@echo "✓ CI pipeline passed"

# ── Security ──────────────────────────────────────────────

harden:
	@echo "→ Hardening file permissions..."
	@test -f .env && chmod 600 .env || true
	@chmod 770 $(BACKEND_DIR)/data
	@mkdir -p $(BACKEND_DIR)/data/logs && chmod 770 $(BACKEND_DIR)/data/logs
	@test -d $(BACKEND_DIR)/certs && chmod 700 $(BACKEND_DIR)/certs || true
	@echo "→ Checking required env vars..."
	@test -f .env && grep -q '^DJANGO_SECRET_KEY=' .env && echo "  DJANGO_SECRET_KEY ✓" || echo "  WARNING: DJANGO_SECRET_KEY not set"
	@test -f .env && grep -q '^DJANGO_ENCRYPTION_KEY=' .env && echo "  DJANGO_ENCRYPTION_KEY ✓" || echo "  WARNING: DJANGO_ENCRYPTION_KEY not set"
	@test -f .env && grep -q '^BACKUP_ENCRYPTION_KEY=' .env && echo "  BACKUP_ENCRYPTION_KEY ✓" || echo "  WARNING: BACKUP_ENCRYPTION_KEY not set"
	@echo "✓ Permissions hardened"

audit:
	@echo "→ Running pip-audit..."
	$(VENV)/bin/pip-audit
	@echo "→ Running npm audit..."
	cd $(FRONTEND_DIR) && npm audit --omit=dev
	@echo "✓ Audit complete"

certs:
	@bash scripts/generate_certs.sh

backup:
	@bash scripts/backup_db.sh

restore:
	@bash scripts/restore_db.sh

analyze:
	cd $(FRONTEND_DIR) && npx vite build
	@echo "✓ Bundle analysis: $(FRONTEND_DIR)/dist/stats.html"

# ── Operational ──────────────────────────────────────────────

maintain-db:
	bash scripts/maintain_db.sh

health-check:
	bash scripts/health_check.sh

clean-data:
	bash scripts/clean_data.sh

# ── Pilot ──────────────────────────────────────────────────

pdf-report:
	$(MANAGE) generate_pdf_report

smoke-test:
	@bash scripts/smoke_test.sh

verify: smoke-test pilot-preflight test-e2e
	@echo "✓ Full operational verification passed"

pilot-preflight:
	$(MANAGE) pilot_preflight

pilot-preflight-json:
	$(MANAGE) pilot_preflight --json

pilot-status:
	$(MANAGE) pilot_status

pilot-status-json:
	$(MANAGE) pilot_status --json

pilot-status-full:
	$(MANAGE) pilot_status --days 14

# ── Watchdog & Automation ─────────────────────────────────────

watchdog:
	$(MANAGE) watchdog

watchdog-fix:
	$(MANAGE) watchdog --fix

watchdog-shell:
	@bash scripts/watchdog.sh --fix

setup-cron:
	@bash scripts/setup_cron.sh

# ── Monitoring ────────────────────────────────────────────────

monitoring:
	@echo "→ Starting dev monitoring (Prometheus :4010, Grafana :4011)..."
	docker compose --profile monitoring up -d
	@echo "  Prometheus: http://localhost:4010"
	@echo "  Grafana:    http://localhost:4011"

monitoring-prod:
	@echo "→ Starting prod monitoring (Prometheus :4110, Grafana :4111)..."
	docker compose --profile prod-monitoring up -d
	@echo "  Prometheus: http://localhost:4110"
	@echo "  Grafana:    http://localhost:4111"

# ── Clean ──────────────────────────────────────────────────

clean:
	rm -rf $(BACKEND_DIR)/.venv
	rm -rf $(BACKEND_DIR)/.pytest_cache
	rm -rf $(BACKEND_DIR)/.ruff_cache
	rm -rf $(BACKEND_DIR)/.mypy_cache
	rm -rf $(BACKEND_DIR)/src/*.egg-info
	rm -rf $(FRONTEND_DIR)/node_modules
	rm -rf $(FRONTEND_DIR)/dist
	@echo "✓ Cleaned"
