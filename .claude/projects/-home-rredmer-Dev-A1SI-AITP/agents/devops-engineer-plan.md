# Jordan — DevOps Engineer Plan

## Role
Infrastructure health, container monitoring, deployment reliability, alerting.

## Current State (2026-04-08)
- Prod: 10 containers running (backend, frontend, postgres, 7 freqtrade)
- Dev: shut down (not needed while in trading phase)
- Backend deadlock fixed: async health endpoint, larger thread pools, HTTP timeout
- Monitoring stack available (Prometheus :4110, Grafana :4111) but may not be running
- Doppler manages secrets (project: aitp, config: dev)

## Daily Checklist
1. All prod containers healthy: `docker ps --filter name=aitp-prod`
2. Backend health: `curl -sf http://localhost:4100/api/health/?detailed=true`
3. All 7 trading APIs responding: curl :4180-4189 /api/v1/ping
4. Disk space adequate (check health endpoint disk.free_gb)
5. No zombie processes: `docker top aitp-prod-backend | wc -l` (should be < 10)
6. Daily PDF report generated: check backend/data/reports/

## Active Plan
| Task | Target Date | Status |
|------|------------|--------|
| Verify monitoring stack (Prometheus/Grafana) is running in prod | 2026-04-09 | NOT STARTED |
| Set up alerting for container health failures | 2026-04-10 | NOT STARTED |
| Add nginx resolver directive to prevent stale DNS on backend restart | 2026-04-10 | NOT STARTED |
| Ensure daily reports are being generated (5PM ET cron) | 2026-04-09 | NOT STARTED |
| Automate frontend restart after backend redeploy | 2026-04-11 | NOT STARTED |

## Key Infrastructure
- Prod ports: backend :4100, frontend :4101, postgres :4112, freqtrade :4180-4189
- Monitoring: Prometheus :4110, Grafana :4111
- Deploy: `doppler run -- docker compose -f docker-compose.prod.yml --profile trading up -d`
- Secrets: Doppler CLI (project: aitp, config: dev)

## Lessons Learned
- Backend deadlocked for 18+ hours (2026-04-08) due to thread pool starvation. Fixed with async health endpoint, 20-thread APScheduler pool, 4 job workers, Daphne -t 30 timeout.
- Frontend nginx caches backend DNS at startup. After backend recreate, must restart frontend.
- Always use `--profile trading` when deploying prod.
