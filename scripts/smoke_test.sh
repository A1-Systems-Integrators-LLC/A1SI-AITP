#!/bin/bash
# smoke_test.sh — Post-deploy API smoke test
# Hits every critical endpoint and fails loudly on any error.
# Usage: make smoke-test  OR  bash scripts/smoke_test.sh [base_url]
set -euo pipefail

BASE_URL="${1:-http://localhost:3000}"
API="${BASE_URL}/api"
PASS=0
FAIL=0
WARN=0
COOKIE_JAR=$(mktemp)
trap 'rm -f "$COOKIE_JAR"' EXIT

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }

check() {
    local name="$1" url="$2" expected_status="${3:-200}" body_check="${4:-}"
    local http_code body
    body=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 -b "$COOKIE_JAR" -c "$COOKIE_JAR" "$url" 2>/dev/null) || body="000"
    http_code="$body"
    if [ "$http_code" != "$expected_status" ]; then
        red "  FAIL [$http_code] $name ($url) — expected $expected_status"
        FAIL=$((FAIL + 1))
        return 1
    fi
    if [ -n "$body_check" ]; then
        local response
        response=$(curl -sS --max-time 10 -b "$COOKIE_JAR" -c "$COOKIE_JAR" "$url" 2>/dev/null)
        if ! echo "$response" | grep -q "$body_check"; then
            red "  FAIL $name — response missing '$body_check'"
            FAIL=$((FAIL + 1))
            return 1
        fi
    fi
    green "  PASS $name"
    PASS=$((PASS + 1))
}

check_warn() {
    local name="$1" url="$2" body_check="${3:-}"
    local http_code
    http_code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null) || http_code="000"
    if [ "$http_code" = "200" ]; then
        if [ -n "$body_check" ]; then
            local response
            response=$(curl -sS --max-time 5 "$url" 2>/dev/null)
            if echo "$response" | grep -q "$body_check"; then
                green "  PASS $name"
                PASS=$((PASS + 1))
                return
            fi
        else
            green "  PASS $name"
            PASS=$((PASS + 1))
            return
        fi
    fi
    yellow "  WARN $name (status=$http_code) — non-fatal"
    WARN=$((WARN + 1))
}

echo "=== Smoke Test ==="
echo "Target: $BASE_URL"
echo ""

# 1. Health check (unauthenticated)
echo "-- Health --"
check "Health endpoint" "$API/health/?detailed=true" 200 '"status"'

# 2. Login
echo "-- Auth --"
LOGIN_RESPONSE=$(curl -sS -c "$COOKIE_JAR" -X POST \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin"}' \
    "$API/auth/login/" 2>/dev/null)
LOGIN_CODE=$(curl -sS -o /dev/null -w "%{http_code}" -c "$COOKIE_JAR" -X POST \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin"}' \
    "$API/auth/login/" 2>/dev/null)

# Extract CSRF token from cookie jar for subsequent requests
CSRF_TOKEN=$(grep -i csrftoken "$COOKIE_JAR" 2>/dev/null | awk '{print $NF}' || true)

if [ "$LOGIN_CODE" = "200" ]; then
    green "  PASS Login"
    PASS=$((PASS + 1))
else
    red "  FAIL Login (status=$LOGIN_CODE)"
    FAIL=$((FAIL + 1))
fi

# 3. Auth session
check "Auth session (GET /api/auth/status/)" "$API/auth/status/" 200

# 4-10. Authenticated endpoints
echo "-- API Endpoints --"
check "Dashboard KPIs" "$API/dashboard/kpis/" 200
check "Risk status" "$API/risk/1/status/" 200
check "Regime current" "$API/regime/current/" 200
check "Jobs list" "$API/jobs/" 200
check "Orders list" "$API/trading/orders/" 200
check "Portfolio list" "$API/portfolio/" 200
check "Scheduler tasks" "$API/scheduler/tasks/" 200

# 11. Freqtrade instances (warn-only)
echo "-- Freqtrade (warn-only) --"
check_warn "Freqtrade CIV1 :8080" "http://localhost:8080/api/v1/ping" "pong"
check_warn "Freqtrade BMR  :8083" "http://localhost:8083/api/v1/ping" "pong"
check_warn "Freqtrade VB   :8084" "http://localhost:8084/api/v1/ping" "pong"

# 12. Frontend
echo "-- Frontend --"
check "Frontend serves HTML" "$BASE_URL/" 200

# Summary
echo ""
echo "=== Results ==="
echo "  Passed:   $PASS"
echo "  Failed:   $FAIL"
echo "  Warnings: $WARN"
echo ""

if [ "$FAIL" -gt 0 ]; then
    red "SMOKE TEST FAILED ($FAIL failures)"
    exit 1
fi

green "SMOKE TEST PASSED"
exit 0
