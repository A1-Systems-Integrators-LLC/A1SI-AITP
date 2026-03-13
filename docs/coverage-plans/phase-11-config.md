# Phase 11: backend/config/ + manage.py (79% → 100%)

**Created**: 2026-03-10
**Target**: 100% line coverage on `backend/config/` and `backend/manage.py`

## Current State

| File | Stmts | Miss | Cover | Missing Lines |
|------|-------|------|-------|---------------|
| `config/__init__.py` | 0 | 0 | 100% | — |
| `config/asgi.py` | 8 | 8 | 0% | 3-16 (module-level imports + app setup) |
| `config/settings.py` | 100 | 8 | 92% | 29 (SECRET_KEY production check), 31 (ENCRYPTION_KEY production check), 167-170 (HSTS/SSL settings), 264-266 (deprecation warning) |
| `config/urls.py` | 5 | 5 | 0% | 1-7 (module-level) |
| `config/wsgi.py` | 4 | 4 | 0% | 3-9 (module-level) |
| `manage.py` | 7 | 7 | 0% | main() function + `__main__` guard |

## Strategy

### Module-level files (asgi.py, wsgi.py, urls.py)
These are exercised by Django's test client (any test using `@pytest.mark.django_db` or `APIClient` loads urls.py). They show 0% because pytest `--cov` only tracks files explicitly in `--cov=backend/config`. We need to either:
- Import them explicitly in tests, OR
- Mark with `pragma: no cover` since they're Django boilerplate

**Decision**: Write explicit import tests for asgi.py and wsgi.py. urls.py is loaded by every Django test — add a simple assertion.

### settings.py uncovered lines
- **Lines 29, 31**: `raise ValueError` when `DEBUG=False` and secrets not set — test with env override
- **Lines 167-170**: HSTS/SSL settings under `not DEBUG` — test with DEBUG=False
- **Lines 264-266**: `warnings.warn` for EXCHANGE_API_KEY env var — test with env override

### manage.py
- **main()**: Standard Django boilerplate — test the function call
- **`__main__`**: Mark `pragma: no cover`

## Test File

`backend/tests/test_config_phase11.py`

## Estimated: ~8 new tests
