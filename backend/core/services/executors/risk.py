"""Risk-related task executors: monitoring, daily reset, equity sync."""

import logging
from typing import Any

from core.services.executors._types import ProgressCallback

logger = logging.getLogger("scheduler")


def _sync_freqtrade_equity() -> dict[str, Any]:
    """Read Freqtrade balance/profit APIs and update RiskState equity.

    Equity = declared_capital (Freqtrade wallets) + crypto_pnl + forex_pnl.
    Every number is auditable: declared capital comes from settings, P&L comes
    from Freqtrade profit API and forex paper trading fills. No phantom capital.

    SAFETY: If no Freqtrade instances respond, skip the update entirely.
    """
    import requests
    from django.conf import settings as django_settings

    ft_instances = getattr(django_settings, "FREQTRADE_INSTANCES", [])
    ft_user = getattr(django_settings, "FREQTRADE_USERNAME", "freqtrader")
    ft_pass = getattr(django_settings, "FREQTRADE_PASSWORD", "freqtrader")

    # Build instance list from settings
    instances_cfg = []
    for inst in ft_instances:
        if not inst.get("enabled", True):
            continue
        url = inst.get("url", "")
        if url:
            instances_cfg.append({
                "name": inst.get("name", ""),
                "url": url,
                "declared_wallet": inst.get("dry_run_wallet", 0),
            })

    # ── Fetch per-instance equity from balance API (preferred) or profit API ──
    instance_results = []
    total_crypto_pnl = 0.0
    declared_capital = 0.0
    open_positions: dict[str, dict] = {}

    for inst in instances_cfg:
        url = inst["url"]
        wallet = inst["declared_wallet"]
        result = {"name": inst["name"], "url": url, "declared_wallet": wallet}

        # Try balance API first (actual wallet total from Freqtrade)
        try:
            bal_resp = requests.get(
                f"{url}/api/v1/balance", auth=(ft_user, ft_pass), timeout=10,
            )
            bal_resp.raise_for_status()
            bal_data = bal_resp.json()
            # total_bot = Freqtrade-managed balance (excludes non-bot funds)
            balance = bal_data.get("total_bot", bal_data.get("total", 0)) or 0
            starting = bal_data.get("starting_capital", wallet) or wallet
            pnl = balance - starting
            total_crypto_pnl += pnl
            declared_capital += wallet
            result.update({
                "status": "ok",
                "source": "balance_api",
                "balance": round(balance, 4),
                "starting_capital": round(starting, 4),
                "pnl": round(pnl, 4),
            })
        except Exception:
            # Fallback: profit API + declared wallet
            try:
                prof_resp = requests.get(
                    f"{url}/api/v1/profit", auth=(ft_user, ft_pass), timeout=10,
                )
                prof_resp.raise_for_status()
                pnl = prof_resp.json().get("profit_all_coin", 0.0)
                total_crypto_pnl += pnl
                declared_capital += wallet
                result.update({
                    "status": "ok",
                    "source": "profit_api",
                    "pnl": round(pnl, 4),
                })
            except Exception as e:
                logger.warning("Freqtrade equity sync failed for %s: %s", url, e)
                result.update({"status": "error", "error": str(e)})

        instance_results.append(result)

    # ── Forex paper trading P&L (from actual filled orders, no phantom capital) ──
    forex_pnl = 0.0
    try:
        from trading.services.forex_paper_trading import ForexPaperTradingService

        forex_svc = ForexPaperTradingService()
        forex_profit = forex_svc.get_profit()
        forex_pnl = forex_profit.get("profit_all_coin", 0.0) or 0.0
        # Include forex open positions in position tracking
        for pos in forex_profit.get("open_positions", []):
            sym = pos.get("symbol", "")
            if sym:
                open_positions[sym] = {
                    "side": pos.get("side", "buy"),
                    "size": pos.get("amount", 0),
                    "entry_price": pos.get("entry_price", 0),
                    "value": pos.get("value", 0),
                }
    except Exception:
        pass

    # ── SAFETY: require at least one instance responded ──
    successful = [r for r in instance_results if r.get("status") == "ok"]
    if not successful and instances_cfg:
        logger.warning(
            "Freqtrade equity sync: 0/%d instances responded — "
            "SKIPPING equity update to prevent corruption",
            len(instances_cfg),
        )
        return {
            "total_pnl": 0.0, "forex_pnl": forex_pnl,
            "equity_updated": False, "skipped_reason": "no_instances_responding",
            "instances": instance_results, "open_positions_count": 0,
        }

    if declared_capital <= 0:
        logger.error(
            "Freqtrade equity sync: declared_capital=$%.2f — "
            "skipping update to prevent corruption", declared_capital,
        )
        return {
            "total_pnl": total_crypto_pnl, "forex_pnl": forex_pnl,
            "equity_updated": False, "skipped_reason": "zero_declared_capital",
            "instances": instance_results, "open_positions_count": 0,
        }

    # ── Compute current equity: declared capital + P&L from all sources ──
    current_equity = declared_capital + total_crypto_pnl + forex_pnl

    from portfolio.models import Portfolio
    from risk.models import CapitalLedger, RiskState
    from risk.services.risk import RiskManagementService

    # ── Sync open positions from Freqtrade instances ──
    for inst in instances_cfg:
        url = inst["url"]
        try:
            resp = requests.get(
                f"{url}/api/v1/status", auth=(ft_user, ft_pass), timeout=10,
            )
            if resp.status_code == 200:
                for trade in resp.json():
                    pair = trade.get("pair", "")
                    if pair:
                        open_positions[pair] = {
                            "side": "buy",
                            "size": trade.get("amount", 0),
                            "entry_price": trade.get("open_rate", 0),
                            "current_price": trade.get("current_rate", 0),
                            "value": trade.get("stake_amount", 0),
                        }
        except Exception as e:
            logger.debug("Failed to fetch open trades from %s: %s", url, e)

    # ── Update RiskState for the crypto portfolio ──
    portfolios = Portfolio.objects.filter(asset_class="crypto")
    if not portfolios.exists():
        portfolios = Portfolio.objects.all()
    portfolio = portfolios.first()
    equity_updated = False

    if portfolio is not None:
        # Swing guard: reject >50% swings UNLESS the new value is close to
        # declared capital (which means we're correcting from a bad state).
        swing_blocked = False
        try:
            state = RiskState.objects.get(portfolio_id=portfolio.id)
            if state.total_equity > 0:
                delta_pct = abs(current_equity - state.total_equity) / state.total_equity
                capital_delta_pct = (
                    abs(current_equity - declared_capital) / declared_capital
                )
                if delta_pct > 0.50 and capital_delta_pct > 0.50:
                    logger.error(
                        "Equity swing guard: new=$%.2f, stored=$%.2f, delta=%.0f%%, "
                        "declared=$%.2f, capital_delta=%.0f%% — BLOCKED",
                        current_equity, state.total_equity, delta_pct * 100,
                        declared_capital, capital_delta_pct * 100,
                    )
                    swing_blocked = True
                elif delta_pct > 0.50:
                    logger.info(
                        "Equity correction: $%.2f → $%.2f (delta=%.0f%%) — "
                        "ALLOWED (close to declared capital $%.2f)",
                        state.total_equity, current_equity, delta_pct * 100,
                        declared_capital,
                    )
        except RiskState.DoesNotExist:
            pass

        if not swing_blocked:
            RiskManagementService.update_equity(portfolio.id, current_equity)
            equity_updated = True
            try:
                state = RiskState.objects.get(portfolio_id=portfolio.id)
                state.daily_pnl = current_equity - state.daily_start_equity
                state.total_pnl = current_equity - declared_capital
                state.crypto_pnl = total_crypto_pnl
                state.forex_pnl = forex_pnl
                state.declared_capital = declared_capital
                state.open_positions = open_positions
                state.save(update_fields=[
                    "daily_pnl", "total_pnl", "crypto_pnl", "forex_pnl",
                    "declared_capital", "open_positions",
                ])
            except RiskState.DoesNotExist:
                pass

            # ── Write audit ledger entry ──
            try:
                CapitalLedger.objects.create(
                    portfolio_id=portfolio.id,
                    entry_type="equity_sync",
                    source="scheduler",
                    amount=current_equity,
                    balance_after=current_equity,
                    details={
                        "declared_capital": declared_capital,
                        "crypto_pnl": round(total_crypto_pnl, 4),
                        "forex_pnl": round(forex_pnl, 4),
                        "instances": [
                            {k: v for k, v in r.items() if k != "url"}
                            for r in instance_results
                        ],
                    },
                )
            except Exception:
                logger.debug("Failed to write capital ledger entry", exc_info=True)

    # Feed current mark prices into ReturnTracker for VaR/correlation.
    if open_positions:
        prices = {
            sym: pos.get("current_price") or pos.get("entry_price", 0)
            for sym, pos in open_positions.items()
            if pos.get("current_price") or pos.get("entry_price")
        }
        if prices:
            RiskManagementService.record_prices(prices)

    return {
        "declared_capital": declared_capital,
        "crypto_pnl": total_crypto_pnl,
        "forex_pnl": forex_pnl,
        "total_pnl": total_crypto_pnl + forex_pnl,
        "current_equity": current_equity,
        "equity_updated": equity_updated,
        "instances": instance_results,
        "open_positions_count": len(open_positions),
    }


def _run_risk_monitoring(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Run periodic risk monitoring across all portfolios."""
    # Sync Freqtrade equity before risk checks
    progress_cb(0.1, "Syncing Freqtrade equity")
    sync_result = None
    equity_sync_failed = False
    try:
        sync_result = _sync_freqtrade_equity()
        logger.info("Equity synced: total_pnl=$%.2f", sync_result.get("total_pnl", 0))
    except Exception as e:
        equity_sync_failed = True
        logger.error(
            "Freqtrade equity sync failed: %s — risk checks will use stale equity data",
            e,
        )

    progress_cb(0.3, "Checking portfolio risk")
    try:
        from portfolio.models import Portfolio
        from risk.services.risk import RiskManagementService

        portfolios = list(Portfolio.objects.values_list("id", flat=True))
        if not portfolios:
            return {"status": "completed", "message": "No portfolios", "equity_sync": sync_result}

        results = []
        for i, pid in enumerate(portfolios):
            try:
                result = RiskManagementService.periodic_risk_check(pid)
                results.append(result)
            except Exception as e:
                logger.error("Risk check failed for portfolio %s: %s", pid, e)
                results.append({"portfolio_id": pid, "status": "error", "error": str(e)})
            progress_cb(0.3 + 0.6 * (i + 1) / len(portfolios), f"Checked portfolio {pid}")

        all_errors = all(
            isinstance(r, dict) and r.get("status") == "error" for r in results
        )
        return {
            "status": "error" if (all_errors and results) else "completed",
            "portfolios_checked": len(portfolios),
            "results": results,
            "equity_sync": sync_result,
            "equity_sync_failed": equity_sync_failed,
        }
    except Exception as e:
        logger.error("Risk monitoring failed: %s", e)
        return {"status": "error", "error": str(e)}


def _run_daily_risk_reset(params: dict, progress_cb: ProgressCallback) -> dict[str, Any]:
    """Reset daily P&L counters for all portfolios.

    Should run once per day (midnight UTC) to prevent stale daily_pnl accumulation.
    """
    from portfolio.models import Portfolio
    from risk.services.risk import RiskManagementService

    progress_cb(0.1, "Resetting daily risk counters")
    portfolios = list(Portfolio.objects.values_list("id", flat=True))

    if not portfolios:
        return {"status": "completed", "message": "No portfolios", "reset_count": 0}

    reset_count = 0
    for i, pid in enumerate(portfolios):
        try:
            RiskManagementService.reset_daily(pid)
            reset_count += 1
            logger.info("Daily risk reset completed for portfolio %s", pid)
        except Exception as e:
            logger.error("Daily risk reset failed for portfolio %s: %s", pid, e)
        progress_cb(0.1 + 0.8 * (i + 1) / len(portfolios), f"Reset {i + 1}/{len(portfolios)}")

    progress_cb(0.9, f"Reset {reset_count} portfolios")
    return {"status": "completed", "reset_count": reset_count, "total_portfolios": len(portfolios)}
