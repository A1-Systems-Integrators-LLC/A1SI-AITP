.PHONY: setup dev test lint build clean harden audit certs backup test-security ci typecheck docker-build check-schema-freshness generate-types install-hooks docker-up docker-down docker-restart docker-deploy docker-logs docker-status docker-clean

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

# ── Docker ────────────────────────────────────────────────

docker-build:
	@echo "→ Building Docker images..."
	docker compose build
	@echo "✓ Docker images built"

docker-build-clean:
	@echo "→ Rebuilding Docker images (no cache)..."
	docker compose build --no-cache
	@echo "✓ Docker images rebuilt"

docker-up:
	@echo "→ Starting containers..."
	docker compose up -d
	@echo "→ Waiting for health checks..."
	@timeout 60 sh -c 'until docker compose ps --format json | grep -q '"'"'"Health":"healthy"'"'"'; do sleep 2; done' 2>/dev/null \
		&& echo "✓ Containers healthy" \
		|| (echo "⚠ Health check timeout — check logs with 'make docker-logs'" && docker compose ps)

docker-down:
	@echo "→ Stopping containers..."
	docker compose down
	@echo "✓ Containers stopped"

docker-restart:
	@echo "→ Restarting containers..."
	$(MAKE) docker-down
	$(MAKE) docker-up

docker-deploy:
	@echo "→ Full deploy: build + restart + verify..."
	$(MAKE) docker-build
	$(MAKE) docker-down
	$(MAKE) docker-up
	@echo "✓ Deploy complete"

docker-deploy-clean:
	@echo "→ Full clean deploy: rebuild + restart + verify..."
	$(MAKE) docker-build-clean
	$(MAKE) docker-down
	$(MAKE) docker-up
	@echo "✓ Clean deploy complete"

docker-logs:
	docker compose logs -f --tail=50

docker-logs-backend:
	docker compose logs -f --tail=50 backend

docker-logs-frontend:
	docker compose logs -f --tail=50 frontend

docker-status:
	@echo "── Container Status ──"
	@docker compose ps
	@echo ""
	@echo "── Health ──"
	@docker inspect --format='{{.Name}}: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' $$(docker compose ps -q 2>/dev/null) 2>/dev/null || echo "No containers running"

docker-clean:
	@echo "→ Removing containers, images, and volumes..."
	docker compose down -v --rmi local
	@echo "✓ Docker artifacts cleaned"

# ── CI pipeline (lint + typecheck + test + audit) ─────────

ci: lint typecheck check-schema-freshness test audit
	@echo "✓ CI pipeline passed"

# ── Security ──────────────────────────────────────────────

harden:
	@echo "→ Hardening file permissions..."
	@test -f .env && chmod 600 .env || true
	@chmod 700 $(BACKEND_DIR)/data
	@mkdir -p $(BACKEND_DIR)/data/logs && chmod 700 $(BACKEND_DIR)/data/logs
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
