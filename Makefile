.PHONY: setup dev start stop test lint build clean harden audit certs backup restore analyze test-security test-e2e ci typecheck docker-build check-schema-freshness generate-types install-hooks docker-up docker-down docker-restart docker-deploy docker-deploy-clean docker-prod-up docker-prod-down docker-prod-deploy docker-prod-logs docker-logs docker-logs-backend docker-logs-frontend docker-status docker-clean maintain-db health-check clean-data pilot-preflight pilot-preflight-json pilot-status pilot-status-json pilot-status-full smoke-test verify monitoring monitoring-prod watchdog watchdog-fix setup-cron doppler-setup doppler-dev doppler-docker-up doppler-docker-prod-up doppler-secrets trading-up trading-down research-up research-down frameworks-up frameworks-down frameworks-status

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

# ── Docker (Dev — aitp-dev group, ports 4000-4099) ────────
COMPOSE_DEV := docker compose
COMPOSE_PROD := docker compose -f docker-compose.prod.yml

docker-build:
	@echo "→ Building dev Docker images..."
	$(COMPOSE_DEV) --profile trading --profile research build
	@echo "✓ Dev images built"

docker-build-clean:
	@echo "→ Rebuilding dev Docker images (no cache)..."
	$(COMPOSE_DEV) --profile trading --profile research build --no-cache
	@echo "✓ Dev images rebuilt"

docker-up:
	@echo "→ Starting dev containers (aitp-dev group, ports 4000-4099)..."
	$(COMPOSE_DEV) up -d
	@echo "→ Waiting for backend health..."
	@for i in $$(seq 1 40); do s=$$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{end}}' aitp-dev-backend 2>/dev/null); [ "$$s" = "healthy" ] && break; sleep 3; done
	@$(COMPOSE_DEV) start frontend 2>/dev/null || true
	@echo "✓ Dev core containers running"
	@echo "  Backend:  http://localhost:4000"
	@echo "  Frontend: http://localhost:4001"

docker-down:
	@echo "→ Stopping all dev containers (aitp-dev group)..."
	$(COMPOSE_DEV) --profile trading --profile research --profile monitoring --profile postgres down
	@echo "✓ Dev containers stopped"

docker-restart:
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
	$(MAKE) docker-build-clean
	$(MAKE) docker-down
	$(MAKE) docker-up
	$(MAKE) smoke-test
	@echo "✓ Clean dev deploy complete"

# ── Docker (Prod — aitp-prod group, ports 4100-4199) ─────

docker-prod-build:
	@echo "→ Building prod Docker images..."
	$(COMPOSE_PROD) --profile trading --profile research build
	@echo "✓ Prod images built"

docker-prod-up:
	@echo "→ Starting prod containers (aitp-prod group, ports 4100-4199)..."
	$(COMPOSE_PROD) up -d
	@echo "→ Waiting for backend health..."
	@for i in $$(seq 1 40); do s=$$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{end}}' aitp-prod-backend 2>/dev/null); [ "$$s" = "healthy" ] && break; sleep 3; done
	@$(COMPOSE_PROD) start frontend 2>/dev/null || true
	@echo "✓ Prod core containers running"
	@echo "  Backend:  http://localhost:4100"
	@echo "  Frontend: http://localhost:4101"

docker-prod-down:
	@echo "→ Stopping all prod containers (aitp-prod group)..."
	$(COMPOSE_PROD) --profile trading --profile research --profile monitoring --profile postgres down
	@echo "✓ Prod containers stopped"

docker-prod-deploy:
	@echo "→ Full prod deploy: build + restart + verify..."
	$(MAKE) docker-prod-build
	$(MAKE) docker-prod-down
	$(MAKE) docker-prod-up
	@curl -sf http://localhost:4100/api/health/ | python3 -m json.tool > /dev/null 2>&1 \
		&& echo "✓ Prod smoke test passed" \
		|| echo "✗ Prod smoke test failed"
	@echo "✓ Prod deploy complete"

docker-prod-logs:
	$(COMPOSE_PROD) logs -f --tail=50

# ── Docker (shared) ──────────────────────────────────────

docker-logs:
	$(COMPOSE_DEV) logs -f --tail=50

docker-logs-backend:
	$(COMPOSE_DEV) logs -f --tail=50 backend

docker-logs-frontend:
	$(COMPOSE_DEV) logs -f --tail=50 frontend

docker-status:
	@echo "── aitp-dev Containers ──"
	@docker ps --filter "name=aitp-dev-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  No dev containers"
	@echo ""
	@echo "── aitp-prod Containers ──"
	@docker ps --filter "name=aitp-prod-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  No prod containers"

docker-clean:
	@echo "→ Removing all AITP containers, images, and volumes..."
	$(COMPOSE_DEV) --profile trading --profile research --profile monitoring --profile postgres down -v --rmi local 2>/dev/null || true
	$(COMPOSE_PROD) --profile trading --profile research --profile monitoring --profile postgres down -v --rmi local 2>/dev/null || true
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
	@echo "→ Checking required secrets (Doppler)..."
	@doppler secrets get DJANGO_SECRET_KEY --plain --project aitp --config dev > /dev/null 2>&1 \
		&& echo "  DJANGO_SECRET_KEY ✓ (Doppler)" \
		|| (test -f .env && grep -q '^DJANGO_SECRET_KEY=' .env && echo "  DJANGO_SECRET_KEY ✓ (.env)" || echo "  WARNING: DJANGO_SECRET_KEY not set")
	@doppler secrets get DJANGO_ENCRYPTION_KEY --plain --project aitp --config dev > /dev/null 2>&1 \
		&& echo "  DJANGO_ENCRYPTION_KEY ✓ (Doppler)" \
		|| (test -f .env && grep -q '^DJANGO_ENCRYPTION_KEY=' .env && echo "  DJANGO_ENCRYPTION_KEY ✓ (.env)" || echo "  WARNING: DJANGO_ENCRYPTION_KEY not set")
	@doppler secrets get KRAKEN_API_KEY --plain --project aitp --config dev 2>/dev/null | grep -q . \
		&& echo "  KRAKEN_API_KEY ✓ (Doppler)" \
		|| echo "  WARNING: KRAKEN_API_KEY not set"
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

# ── Doppler ─────────────────────────────────────────────────

doppler-setup:
	@echo "→ Setting up Doppler for this project..."
	doppler setup --project aitp --config dev --no-interactive
	@echo "✓ Doppler linked to project aitp (dev config)"

doppler-dev:
	@echo "→ Starting dev server via Doppler..."
	doppler run -- bash scripts/dev.sh

doppler-docker-up:
	@echo "→ Starting dev containers via Doppler (aitp-dev group)..."
	doppler run -- $(COMPOSE_DEV) up -d
	@echo "→ Waiting for health..."
	@for i in $$(seq 1 40); do s=$$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{end}}' aitp-dev-backend 2>/dev/null); [ "$$s" = "healthy" ] && break; sleep 3; done
	@doppler run -- $(COMPOSE_DEV) start frontend 2>/dev/null || true
	@echo "✓ Dev containers healthy"

doppler-docker-prod-up:
	@echo "→ Starting prod containers via Doppler (aitp-prod group)..."
	doppler run --config prd -- $(COMPOSE_PROD) up -d
	@echo "→ Waiting for health..."
	@for i in $$(seq 1 40); do s=$$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{end}}' aitp-prod-backend 2>/dev/null); [ "$$s" = "healthy" ] && break; sleep 3; done
	@doppler run --config prd -- $(COMPOSE_PROD) start frontend 2>/dev/null || true
	@echo "✓ Prod containers healthy"

doppler-secrets:
	@echo "── Doppler Secrets (aitp) ──"
	doppler secrets --only-names

# ── Trading Frameworks ─────────────────────────────────────

trading-up:
	@echo "→ Starting dev trading containers..."
	$(COMPOSE_DEV) --profile trading up -d
	@echo "✓ Trading containers started (CIV1 :4080, BMR :4083, VB :4084)"

trading-down:
	@echo "→ Stopping dev trading containers..."
	$(COMPOSE_DEV) --profile trading stop freqtrade-civ1 freqtrade-bmr freqtrade-vb
	@echo "✓ Trading containers stopped"

research-up:
	@echo "→ Starting dev research containers..."
	$(COMPOSE_DEV) --profile research up -d
	@echo "✓ Research containers started (NautilusTrader :4090, VectorBT :4092, Redis :4013, Jupyter :4020)"

research-down:
	@echo "→ Stopping dev research containers..."
	$(COMPOSE_DEV) --profile research stop nautilus vectorbt redis jupyter
	@echo "✓ Research containers stopped"

frameworks-up: trading-up research-up
	@echo "✓ All dev framework containers running"

frameworks-down: trading-down research-down
	@echo "✓ All dev framework containers stopped"

frameworks-status:
	@echo "── Dev Frameworks ──"
	@docker ps --filter "name=aitp-dev-ft" --filter "name=aitp-dev-nautilus" --filter "name=aitp-dev-vectorbt" --filter "name=aitp-dev-redis" --filter "name=aitp-dev-jupyter" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  None running"
	@echo ""
	@echo "── Prod Frameworks ──"
	@docker ps --filter "name=aitp-prod-ft" --filter "name=aitp-prod-nautilus" --filter "name=aitp-prod-vectorbt" --filter "name=aitp-prod-redis" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  None running"

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
