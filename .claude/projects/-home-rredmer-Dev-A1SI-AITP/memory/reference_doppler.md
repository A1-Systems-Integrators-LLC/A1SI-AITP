---
name: Doppler Secrets
description: Secrets managed via Doppler CLI — project aitp, config dev/prod
type: reference
---

Secrets are managed via Doppler (not .env files).

- Project: `aitp`
- Config: `dev` (for dev stack)
- Usage: `doppler run -- docker compose ...`
- Key vars: DJANGO_SECRET_KEY, DJANGO_ENCRYPTION_KEY, FREQTRADE_USERNAME, FREQTRADE_PASSWORD, KRAKEN_API_KEY, KRAKEN_SECRET, POSTGRES_PASSWORD

The prod stack runs via systemd/Doppler. Dev stack requires `doppler run --` prefix for all docker compose commands.
