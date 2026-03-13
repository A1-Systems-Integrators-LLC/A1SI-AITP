"""A1SI-AITP Monitoring Dashboard — Streamlit app.

Displays platform health, risk metrics, portfolio status, and recent
trading activity by polling the backend REST API.
"""

import os
import time

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "30"))

st.set_page_config(page_title="A1SI-AITP Monitor", layout="wide")


# ── Helpers ──────────────────────────────────────────────────────────


def api_get(path: str) -> dict | list | None:
    """GET from backend API. Returns None on failure."""
    try:
        resp = requests.get(f"{BACKEND_URL}/api{path}", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        st.error(f"API error ({path}): {exc}")
        return None


# ── Layout ───────────────────────────────────────────────────────────


st.title("A1SI-AITP Platform Monitor")

# Platform status
status = api_get("/platform/status/")
if status:
    cols = st.columns(3)
    cols[0].metric("Frameworks", len(status.get("frameworks", [])))
    cols[1].metric("Data Files", status.get("data_files", 0))
    cols[2].metric("Active Jobs", status.get("active_jobs", 0))

    with st.expander("Framework Details"):
        for fw in status.get("frameworks", []):
            icon = "✅" if fw.get("installed") else "❌"
            st.write(f"{icon} **{fw['name']}** — {fw.get('version', 'n/a')}")

st.divider()

# Risk + Portfolio side-by-side
left, right = st.columns(2)

with left:
    st.subheader("Risk Status")
    risk = api_get("/risk/1/status/")
    if risk:
        r1, r2 = st.columns(2)
        r1.metric("Equity", f"${risk.get('equity', 0):,.2f}")
        r2.metric("Drawdown", f"{risk.get('drawdown', 0):.2%}")
        halted = risk.get("is_halted", False)
        st.warning(f"HALTED — {risk.get('halt_reason', '')}") if halted else st.success("Trading active")

    heat = api_get("/risk/1/heat-check/")
    if heat:
        healthy = heat.get("healthy", True)
        st.success("Portfolio healthy") if healthy else st.error("Issues detected")
        for issue in heat.get("issues", []):
            st.write(f"- {issue}")

with right:
    st.subheader("Portfolios")
    portfolios = api_get("/portfolios/")
    if portfolios:
        for p in portfolios[:5]:
            st.write(f"**{p['name']}** (id={p['id']}) — {len(p.get('holdings', []))} holdings")
    else:
        st.info("No portfolios found")

st.divider()

# Recent orders
st.subheader("Recent Orders")
orders = api_get("/trading/orders/?limit=10")
if orders:
    st.table(
        [
            {
                "ID": o["id"],
                "Symbol": o["symbol"],
                "Side": o["side"],
                "Amount": o["amount"],
                "Status": o["status"],
                "Mode": o["mode"],
            }
            for o in orders
        ],
    )
else:
    st.info("No orders")

# Auto-refresh
st.caption(f"Auto-refresh every {REFRESH_SECONDS}s")
time.sleep(REFRESH_SECONDS)
st.rerun()
