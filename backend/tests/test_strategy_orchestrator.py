"""Tests for IEB Phase 8: Strategy Orchestrator.

Covers:
- StrategyOrchestrator service (evaluate, state persistence, transitions)
- AlertLog logging on transitions
- WS broadcast on transitions
- Telegram notifications for pause/resume
- Freqtrade pause check integration (_conviction_helpers.check_strategy_paused)
- Task registry executor (_run_strategy_orchestration)
- StrategyStatusView orchestrator integration
- Scheduled task config
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.contrib.auth.models import User
from rest_framework.test import APIClient

from risk.models import AlertLog
from trading.services.strategy_orchestrator import (
    ACTION_ACTIVE,
    ACTION_PAUSE,
    ACTION_REDUCE_SIZE,
    StrategyOrchestrator,
    StrategyState,
)


@pytest.fixture(autouse=True)
def _reset_orchestrator(tmp_path):
    """Reset singleton before each test, redirect persistence to tmp."""
    StrategyOrchestrator.reset_instance()
    original = StrategyOrchestrator._STATE_FILE
    StrategyOrchestrator._STATE_FILE = tmp_path / "orchestrator_state.json"
    yield
    StrategyOrchestrator.reset_instance()
    StrategyOrchestrator._STATE_FILE = original


@pytest.fixture
def orchestrator():
    return StrategyOrchestrator()


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user("testuser", password="testpass")
    client = APIClient()
    client.force_authenticate(user)
    return client


# ── StrategyState dataclass ──────────────────────────────────────


class TestStrategyState:
    def test_state_creation(self):
        state = StrategyState(
            strategy="CryptoInvestorV1",
            asset_class="crypto",
            regime="STRONG_TREND_UP",
            alignment=95,
            action=ACTION_ACTIVE,
        )
        assert state.strategy == "CryptoInvestorV1"
        assert state.action == ACTION_ACTIVE
        assert state.updated_at is not None


# ── Singleton ──────────────────────────────────────────────────


class TestSingleton:
    def test_get_instance_returns_same(self):
        a = StrategyOrchestrator.get_instance()
        b = StrategyOrchestrator.get_instance()
        assert a is b

    def test_reset_instance(self):
        a = StrategyOrchestrator.get_instance()
        StrategyOrchestrator.reset_instance()
        b = StrategyOrchestrator.get_instance()
        assert a is not b


# ── State management ──────────────────────────────────────────


class TestStateManagement:
    def test_get_state_none_initially(self, orchestrator):
        assert orchestrator.get_state("CryptoInvestorV1", "crypto") is None

    def test_get_all_states_empty(self, orchestrator):
        assert orchestrator.get_all_states() == []

    def test_is_paused_false_when_unknown(self, orchestrator):
        assert orchestrator.is_paused("CryptoInvestorV1", "crypto") is False

    def test_get_size_modifier_default(self, orchestrator):
        assert orchestrator.get_size_modifier("CryptoInvestorV1", "crypto") == 1.0

    def test_classify_action_pause(self, orchestrator):
        assert orchestrator._classify_action(15) == ACTION_PAUSE
        assert orchestrator._classify_action(3) == ACTION_PAUSE
        assert orchestrator._classify_action(10) == ACTION_PAUSE

    def test_classify_action_reduce(self, orchestrator):
        assert orchestrator._classify_action(35) == ACTION_REDUCE_SIZE
        assert orchestrator._classify_action(20) == ACTION_REDUCE_SIZE

    def test_classify_action_active(self, orchestrator):
        assert orchestrator._classify_action(36) == ACTION_ACTIVE
        assert orchestrator._classify_action(95) == ACTION_ACTIVE


# ── Evaluate ──────────────────────────────────────────────────


class TestEvaluate:
    @patch("trading.services.strategy_orchestrator.StrategyOrchestrator._broadcast")
    @patch("trading.services.strategy_orchestrator.StrategyOrchestrator._log_alert")
    @patch("trading.services.strategy_orchestrator.StrategyOrchestrator._notify_telegram")
    def test_evaluate_with_mocked_regime(self, mock_tg, mock_alert, mock_ws, orchestrator):
        """Test evaluation with mocked regime detector."""
        mock_state = MagicMock()
        mock_state.regime.value = "STRONG_TREND_UP"

        mock_detector = MagicMock()
        mock_detector.detect.return_value = mock_state

        alignment_table = {
            "crypto": {
                mock_state.regime: {
                    "CryptoInvestorV1": 95,
                    "BollingerMeanReversion": 10,
                    "VolatilityBreakout": 60,
                },
            },
        }

        with (
            patch("trading.services.strategy_orchestrator.StrategyOrchestrator._on_transition"),
            patch("core.platform_bridge.ensure_platform_imports"),
            patch.dict("sys.modules", {
                "common.regime.regime_detector": MagicMock(RegimeDetector=lambda: mock_detector),
                "common.signals.constants": MagicMock(ALIGNMENT_TABLES=alignment_table),
            }),
        ):
            results = orchestrator.evaluate(asset_classes=["crypto"])

        assert len(results) == 3
        civ1 = next(r for r in results if r["strategy"] == "CryptoInvestorV1")
        assert civ1["action"] == ACTION_ACTIVE
        assert civ1["alignment"] == 95

        bmr = next(r for r in results if r["strategy"] == "BollingerMeanReversion")
        assert bmr["action"] == ACTION_PAUSE

        vb = next(r for r in results if r["strategy"] == "VolatilityBreakout")
        assert vb["action"] == ACTION_ACTIVE

    def test_evaluate_fallback_on_error(self, orchestrator):
        """On error, all strategies default to active."""
        with patch("core.platform_bridge.ensure_platform_imports", side_effect=ImportError("no")):
            results = orchestrator.evaluate(asset_classes=["crypto"])

        assert len(results) == 3
        for r in results:
            assert r["action"] == ACTION_ACTIVE
            assert r["regime"] == "unknown"
            assert r["alignment"] == 50

    def test_evaluate_all_asset_classes(self, orchestrator):
        """Evaluate all 3 asset classes — 7 strategies total."""
        with patch("core.platform_bridge.ensure_platform_imports", side_effect=ImportError("no")):
            results = orchestrator.evaluate()

        assert len(results) == 7
        asset_classes = {r["asset_class"] for r in results}
        assert asset_classes == {"crypto", "equity", "forex"}


# ── State persistence after evaluate ──────────────────────────


class TestStatePersistence:
    def test_state_persisted_after_evaluate(self, orchestrator):
        with patch("core.platform_bridge.ensure_platform_imports", side_effect=ImportError("no")):
            orchestrator.evaluate(asset_classes=["crypto"])

        state = orchestrator.get_state("CryptoInvestorV1", "crypto")
        assert state is not None
        assert state.action == ACTION_ACTIVE

        states = orchestrator.get_all_states()
        assert len(states) == 3

    def test_is_paused_after_pause_state(self, orchestrator):
        """Manually set a paused state and verify is_paused."""
        orchestrator._states["CryptoInvestorV1:crypto"] = StrategyState(
            strategy="CryptoInvestorV1",
            asset_class="crypto",
            regime="STRONG_TREND_DOWN",
            alignment=0,
            action=ACTION_PAUSE,
        )
        assert orchestrator.is_paused("CryptoInvestorV1", "crypto") is True

    def test_size_modifier_pause(self, orchestrator):
        orchestrator._states["CryptoInvestorV1:crypto"] = StrategyState(
            strategy="CryptoInvestorV1",
            asset_class="crypto",
            regime="STRONG_TREND_DOWN",
            alignment=0,
            action=ACTION_PAUSE,
        )
        assert orchestrator.get_size_modifier("CryptoInvestorV1", "crypto") == 0.0

    def test_size_modifier_reduce(self, orchestrator):
        orchestrator._states["CryptoInvestorV1:crypto"] = StrategyState(
            strategy="CryptoInvestorV1",
            asset_class="crypto",
            regime="HIGH_VOLATILITY",
            alignment=25,
            action=ACTION_REDUCE_SIZE,
        )
        assert orchestrator.get_size_modifier("CryptoInvestorV1", "crypto") == 0.5


# ── Transition handling ──────────────────────────────────────

_P_BC = "trading.services.strategy_orchestrator.StrategyOrchestrator._broadcast"
_P_TG = "trading.services.strategy_orchestrator.StrategyOrchestrator._notify_telegram"
_P_AL = "trading.services.strategy_orchestrator.StrategyOrchestrator._log_alert"
_P_WS = "core.services.ws_broadcast.broadcast_strategy_status"
_P_TG_SEND = "core.services.notification.send_telegram_rate_limited"


@pytest.mark.django_db
class TestTransitions:
    def test_transition_logs_alert(self, orchestrator):
        """Transition from active to pause should create AlertLog."""
        with patch(_P_BC), patch(_P_TG):
            orchestrator._update_strategy(
                "CryptoInvestorV1", "crypto", "STRONG_TREND_DOWN",
                5, ACTION_PAUSE,
            )

        alerts = AlertLog.objects.filter(event_type="strategy_orchestration")
        assert alerts.count() == 1
        alert = alerts.first()
        assert "active → pause" in alert.message
        assert alert.severity == "warning"

    def test_transition_resume_logs_info(self, orchestrator):
        """Transition from pause to active should log as info."""
        orchestrator._states["CryptoInvestorV1:crypto"] = StrategyState(
            strategy="CryptoInvestorV1",
            asset_class="crypto",
            regime="STRONG_TREND_DOWN",
            alignment=0,
            action=ACTION_PAUSE,
        )

        with patch(_P_BC), patch(_P_TG):
            orchestrator._update_strategy(
                "CryptoInvestorV1", "crypto", "STRONG_TREND_UP",
                95, ACTION_ACTIVE,
            )

        alerts = AlertLog.objects.filter(event_type="strategy_orchestration")
        assert alerts.count() == 1
        alert = alerts.first()
        assert "pause → active" in alert.message
        assert alert.severity == "info"

    def test_no_alert_on_repeated_same_action(self, orchestrator):
        """Second call with same action creates no extra AlertLog."""
        with patch(_P_BC), patch(_P_TG):
            orchestrator._update_strategy(
                "CryptoInvestorV1", "crypto", "STRONG_TREND_UP",
                95, ACTION_ACTIVE,
            )
            count_after_first = AlertLog.objects.filter(
                event_type="strategy_orchestration",
            ).count()

            orchestrator._update_strategy(
                "CryptoInvestorV1", "crypto", "STRONG_TREND_UP",
                95, ACTION_ACTIVE,
            )
            count_after_second = AlertLog.objects.filter(
                event_type="strategy_orchestration",
            ).count()

        assert count_after_second == count_after_first

    def test_broadcast_on_transition(self, orchestrator):
        with patch(_P_TG), patch(_P_WS) as mock_broadcast:
            orchestrator._update_strategy(
                "CryptoInvestorV1", "crypto", "STRONG_TREND_DOWN",
                5, ACTION_PAUSE,
            )

        mock_broadcast.assert_called_once_with(
            strategy="CryptoInvestorV1",
            asset_class="crypto",
            regime="STRONG_TREND_DOWN",
            alignment=5,
            action=ACTION_PAUSE,
        )

    def test_telegram_on_pause(self, orchestrator):
        with patch(_P_BC), patch(_P_TG_SEND) as mock_tg:
            orchestrator._update_strategy(
                "CryptoInvestorV1", "crypto", "STRONG_TREND_DOWN",
                5, ACTION_PAUSE,
            )

        mock_tg.assert_called_once()
        call_msg = mock_tg.call_args[0][0]
        assert "PAUSED" in call_msg

    def test_telegram_on_resume(self, orchestrator):
        orchestrator._states["CryptoInvestorV1:crypto"] = StrategyState(
            strategy="CryptoInvestorV1",
            asset_class="crypto",
            regime="STRONG_TREND_DOWN",
            alignment=0,
            action=ACTION_PAUSE,
        )

        with patch(_P_BC), patch(_P_TG_SEND) as mock_tg:
            orchestrator._update_strategy(
                "CryptoInvestorV1", "crypto", "STRONG_TREND_UP",
                95, ACTION_ACTIVE,
            )

        mock_tg.assert_called_once()
        call_msg = mock_tg.call_args[0][0]
        assert "RESUMED" in call_msg


# ── WS broadcast helper ──────────────────────────────────────


class TestWSBroadcast:
    def test_broadcast_strategy_status(self):
        with patch("core.services.ws_broadcast._send") as mock_send:
            from core.services.ws_broadcast import broadcast_strategy_status

            broadcast_strategy_status(
                strategy="CryptoInvestorV1",
                asset_class="crypto",
                regime="STRONG_TREND_DOWN",
                alignment=5,
                action="pause",
            )
            mock_send.assert_called_once()
            args = mock_send.call_args
            assert args[0][0] == "strategy_status"
            data = args[0][1]
            assert data["strategy"] == "CryptoInvestorV1"
            assert data["action"] == "pause"


# ── Task registry executor ────────────────────────────────────


class TestTaskExecutor:
    def test_executor_delegates_to_orchestrator(self):
        from core.services.task_registry import _run_strategy_orchestration

        mock_orchestrator = MagicMock()
        mock_orchestrator.evaluate.return_value = [
            {"strategy": "CryptoInvestorV1", "action": "active", "transitioned": False},
            {"strategy": "BollingerMeanReversion", "action": "pause", "transitioned": True},
        ]

        with patch(
            "trading.services.strategy_orchestrator.StrategyOrchestrator.get_instance",
            return_value=mock_orchestrator,
        ):
            result = _run_strategy_orchestration({}, lambda p, m: None)

        assert result["status"] == "completed"
        assert result["strategies_evaluated"] == 2
        assert result["paused"] == 1
        assert result["transitioned"] == 1

    def test_executor_passes_asset_classes(self):
        from core.services.task_registry import _run_strategy_orchestration

        mock_orchestrator = MagicMock()
        mock_orchestrator.evaluate.return_value = []

        with patch(
            "trading.services.strategy_orchestrator.StrategyOrchestrator.get_instance",
            return_value=mock_orchestrator,
        ):
            _run_strategy_orchestration(
                {"asset_classes": ["crypto"]}, lambda p, m: None,
            )

        mock_orchestrator.evaluate.assert_called_once_with(asset_classes=["crypto"])


# ── StrategyStatusView API ────────────────────────────────────


@pytest.mark.django_db
class TestStrategyStatusViewOrchestrator:
    def test_returns_orchestrator_state(self, auth_client):
        """View returns orchestrator persisted state when available."""
        orchestrator = StrategyOrchestrator.get_instance()
        orchestrator._states["CryptoInvestorV1:crypto"] = StrategyState(
            strategy="CryptoInvestorV1",
            asset_class="crypto",
            regime="STRONG_TREND_DOWN",
            alignment=5,
            action=ACTION_PAUSE,
        )
        orchestrator._states["BollingerMeanReversion:crypto"] = StrategyState(
            strategy="BollingerMeanReversion",
            asset_class="crypto",
            regime="STRONG_TREND_DOWN",
            alignment=40,
            action=ACTION_ACTIVE,
        )

        resp = auth_client.get("/api/signals/strategy-status/?asset_class=crypto")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        paused = [d for d in data if d["recommended_action"] == "pause"]
        assert len(paused) == 1
        assert paused[0]["strategy_name"] == "CryptoInvestorV1"

    def test_falls_back_to_fresh_when_no_state(self, auth_client):
        """View falls back to fresh computation when orchestrator has no state."""
        with patch("core.platform_bridge.ensure_platform_imports", side_effect=ImportError):
            resp = auth_client.get("/api/signals/strategy-status/?asset_class=crypto")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        for entry in data:
            assert entry["recommended_action"] == "active"
            assert entry["regime"] == "unknown"


# ── Scheduled task config ─────────────────────────────────────


class TestScheduledTaskConfig:
    def test_strategy_orchestration_in_scheduled_tasks(self):
        from django.conf import settings

        assert "strategy_orchestration" in settings.SCHEDULED_TASKS
        task = settings.SCHEDULED_TASKS["strategy_orchestration"]
        assert task["task_type"] == "strategy_orchestration"
        assert task["interval_seconds"] == 900

    def test_strategy_orchestration_in_task_registry(self):
        from core.services.task_registry import TASK_REGISTRY

        assert "strategy_orchestration" in TASK_REGISTRY


# ── Freqtrade pause check ────────────────────────────────────


class TestFreqtradePauseCheck:
    """Tests for _conviction_helpers.check_strategy_paused.

    RunMode is imported inside the function via ``from freqtrade.enums import RunMode``.
    We patch it at the freqtrade.enums level so the import inside the function picks
    up our mock.
    """

    @pytest.fixture(autouse=True)
    def _setup_path(self):
        p = str(PROJECT_ROOT / "freqtrade" / "user_data" / "strategies")
        sys.path.insert(0, p)
        # Remove cached module so each test gets a fresh import
        sys.modules.pop("_conviction_helpers", None)
        yield
        sys.path.remove(p)
        sys.modules.pop("_conviction_helpers", None)

    def _make_strategy(self, name="CryptoInvestorV1", backtest=False):
        strategy = MagicMock()
        strategy.__class__ = type(name, (), {})  # real __name__
        strategy.risk_api_url = "http://localhost:8000"
        strategy._pause_cache = {}

        # Create a RunMode-like enum for the mock
        if backtest:
            # runmode will == BACKTEST
            sentinel = object()
            strategy.dp.runmode = sentinel
            return strategy, sentinel
        strategy.dp.runmode = MagicMock()
        return strategy, None

    def test_check_strategy_paused_in_backtest(self):
        """Should return False (not paused) in backtest mode."""
        strategy, sentinel = self._make_strategy(backtest=True)

        mock_runmode = MagicMock()
        mock_runmode.BACKTEST = sentinel
        mock_runmode.HYPEROPT = MagicMock()

        with patch.dict("sys.modules", {"freqtrade.enums": MagicMock(RunMode=mock_runmode)}):
            from _conviction_helpers import check_strategy_paused
            result = check_strategy_paused(strategy)

        assert result is False

    def test_check_strategy_paused_api_returns_pause(self):
        """Should return True when API says strategy is paused."""
        strategy, _ = self._make_strategy()

        mock_runmode = MagicMock()
        mock_runmode.BACKTEST = MagicMock()
        mock_runmode.HYPEROPT = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "strategy_name": "CryptoInvestorV1",
                "recommended_action": "pause",
                "regime": "STRONG_TREND_DOWN",
                "alignment_score": 5,
            },
        ]

        with patch.dict("sys.modules", {"freqtrade.enums": MagicMock(RunMode=mock_runmode)}):
            from _conviction_helpers import check_strategy_paused
            with patch("requests.get", return_value=mock_resp):
                result = check_strategy_paused(strategy)

        assert result is True

    def test_check_strategy_paused_api_failure_failopen(self):
        """Should return False (fail-open) when API unreachable."""
        strategy, _ = self._make_strategy()

        mock_runmode = MagicMock()
        mock_runmode.BACKTEST = MagicMock()
        mock_runmode.HYPEROPT = MagicMock()

        with patch.dict("sys.modules", {"freqtrade.enums": MagicMock(RunMode=mock_runmode)}):
            from _conviction_helpers import check_strategy_paused
            with patch("requests.get", side_effect=Exception("timeout")):
                result = check_strategy_paused(strategy)

        assert result is False

    def test_check_conviction_calls_pause_check(self):
        """check_conviction should call check_strategy_paused first."""
        mock_runmode = MagicMock()
        mock_runmode.BACKTEST = MagicMock()
        mock_runmode.HYPEROPT = MagicMock()
        ft_mod = MagicMock(RunMode=mock_runmode)

        with patch.dict("sys.modules", {"freqtrade.enums": ft_mod}):
            import _conviction_helpers
            with patch.object(
                _conviction_helpers, "check_strategy_paused",
                return_value=True,
            ) as mock_pause:
                strategy = MagicMock()
                strategy.__class__.__name__ = "CryptoInvestorV1"
                strategy._signals = {
                    "BTC/USDT": {"approved": True, "score": 80},
                }
                strategy.risk_api_url = "http://localhost:8000"

                result = _conviction_helpers.check_conviction(
                    strategy, "BTC/USDT",
                )

            mock_pause.assert_called_once_with(strategy)
            assert result is False  # Paused → rejected

    def test_check_strategy_paused_uses_cache(self):
        """Should use cached pause status within 60s."""
        import time

        strategy, _ = self._make_strategy()
        strategy._pause_cache = {
            "CryptoInvestorV1": {"paused": True, "ts": time.monotonic()},
        }

        mock_runmode = MagicMock()
        mock_runmode.BACKTEST = MagicMock()
        mock_runmode.HYPEROPT = MagicMock()

        with patch.dict("sys.modules", {"freqtrade.enums": MagicMock(RunMode=mock_runmode)}):
            from _conviction_helpers import check_strategy_paused
            result = check_strategy_paused(strategy)

        assert result is True


# ── Error handling ────────────────────────────────────────────


@pytest.mark.django_db
class TestErrorHandling:
    def test_alert_log_failure_doesnt_crash(self, orchestrator):
        """AlertLog failure is caught and logged."""
        with patch("risk.models.AlertLog.objects") as mock_qs:
            mock_qs.create.side_effect = Exception("DB error")
            with patch(_P_BC), patch(_P_TG):
                orchestrator._update_strategy(
                    "CryptoInvestorV1", "crypto",
                    "STRONG_TREND_DOWN", 5, ACTION_PAUSE,
                )

    def test_broadcast_failure_doesnt_crash(self, orchestrator):
        with (
            patch(_P_WS, side_effect=Exception("WS error")),
            patch(_P_TG),
            patch(_P_AL),
        ):
            orchestrator._update_strategy(
                "CryptoInvestorV1", "crypto",
                "STRONG_TREND_DOWN", 5, ACTION_PAUSE,
            )

    def test_telegram_failure_doesnt_crash(self, orchestrator):
        with (
            patch(_P_BC),
            patch(_P_AL),
            patch(_P_TG_SEND, side_effect=Exception("TG err")),
        ):
            orchestrator._update_strategy(
                "CryptoInvestorV1", "crypto",
                "STRONG_TREND_DOWN", 5, ACTION_PAUSE,
            )
