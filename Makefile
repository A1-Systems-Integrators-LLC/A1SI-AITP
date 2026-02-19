.PHONY: setup dev test lint build clean harden audit certs backup test-security

BACKEND_DIR := backend
FRONTEND_DIR := frontend
VENV := $(BACKEND_DIR)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
MANAGE := cd $(BACKEND_DIR) && $(CURDIR)/$(PYTHON) manage.py

# ── Setup ──────────────────────────────────────────────────

setup: setup-backend setup-frontend
	@echo "✓ Setup complete"

setup-backend:
	@echo "→ Setting up backend..."
	@if [ ! -d "$(VENV)" ]; then \
		python3 -m venv --without-pip $(VENV) && \
		curl -sS https://bootstrap.pypa.io/get-pip.py | $(PYTHON); \
	fi
	$(PIP) install -e "$(BACKEND_DIR)[dev]" --quiet
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

lint: lint-backend lint-frontend
	@echo "✓ All linting passed"

lint-backend:
	$(VENV)/bin/ruff check $(BACKEND_DIR)/core/ $(BACKEND_DIR)/portfolio/ $(BACKEND_DIR)/trading/ $(BACKEND_DIR)/market/ $(BACKEND_DIR)/risk/ $(BACKEND_DIR)/analysis/ $(BACKEND_DIR)/tests/ common/ nautilus/ hftbacktest/ research/

lint-frontend:
	cd $(FRONTEND_DIR) && npx eslint .

# ── Build ──────────────────────────────────────────────────

build:
	cd $(FRONTEND_DIR) && npm run build
	@echo "✓ Frontend built to $(FRONTEND_DIR)/dist/"

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
