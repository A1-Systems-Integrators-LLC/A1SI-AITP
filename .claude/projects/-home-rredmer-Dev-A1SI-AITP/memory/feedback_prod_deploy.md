---
name: Always start prod with --profile trading
description: Prod trading strategies require explicit --profile trading flag; omitting it leaves the platform not trading
type: feedback
---

When deploying prod, always use `--profile trading` to start all Freqtrade strategy containers. Without it, only core services (backend, frontend, postgres) start — the trading strategies are behind a Docker Compose profile.

**Why:** On 2026-04-08, prod was found with only 1 of 7 trading strategies running because the previous deploy omitted `--profile trading` for the full set.

**How to apply:** Every `docker compose -f docker-compose.prod.yml up -d` command must include `--profile trading`. The Makefile targets `docker-prod-up` and `docker-prod-deploy` should be used instead of raw docker compose commands.
