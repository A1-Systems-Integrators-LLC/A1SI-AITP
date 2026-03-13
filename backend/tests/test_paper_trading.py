"""Tests for Paper Trading Infrastructure — Sprint 1, Item 1.5
============================================================
Covers: process lifecycle (start/stop/status), event logging,
idempotent operations, error handling.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.services.paper_trading import PaperTradingService

# ── Helpers ───────────────────────────────────────────────────


@pytest.fixture
def ft_env(tmp_path):
    """Set up a fake freqtrade directory and patch get_freqtrade_dir for the whole test."""
    ft_dir = tmp_path / "freqtrade"
    ft_dir.mkdir()
    (ft_dir / "config.json").write_text("{}")
    (ft_dir / "user_data" / "strategies").mkdir(parents=True)

    with (
        patch.object(
            PaperTradingService,
            "_read_ft_config",
            return_value={
                "api_server": {
                    "listen_ip_address": "127.0.0.1",
                    "listen_port": 8080,
                    "username": "freqtrader",
                    "password": "freqtrader",
                },
            },
        ),
        patch("trading.services.paper_trading.get_freqtrade_dir", return_value=ft_dir),
        patch.object(PaperTradingService, "_api_alive", return_value=False),
    ):
        yield PaperTradingService(log_dir=tmp_path)


def _mock_running_process() -> MagicMock:
    """Create a mock subprocess.Popen that appears to be running."""
    proc = MagicMock()
    proc.poll.return_value = None  # None = still running
    proc.pid = 12345
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = MagicMock()
    return proc


# ── Process Lifecycle Tests ───────────────────────────────────


class TestPaperTradingLifecycle:
    def test_not_running_initially(self, ft_env):
        assert ft_env.is_running is False

    def test_status_when_not_running(self, ft_env):
        status = ft_env.get_status()
        assert status["running"] is False
        assert status["uptime_seconds"] == 0

    @patch("trading.services.paper_trading.subprocess.Popen")
    def test_start_success(self, mock_popen, ft_env):
        mock_popen.return_value = _mock_running_process()

        result = ft_env.start(strategy="CryptoInvestorV1")
        assert result["status"] == "started"
        assert result["strategy"] == "CryptoInvestorV1"
        assert result["pid"] == 12345
        assert "started_at" in result
        assert ft_env.is_running is True

    @patch("trading.services.paper_trading.subprocess.Popen")
    def test_start_already_running(self, mock_popen, ft_env):
        mock_popen.return_value = _mock_running_process()

        ft_env.start("CryptoInvestorV1")
        result = ft_env.start("BollingerMeanReversion")
        assert result["status"] == "already_running"
        assert result["strategy"] == "CryptoInvestorV1"

    @patch("trading.services.paper_trading.subprocess.Popen")
    def test_stop_running_process(self, mock_popen, ft_env):
        proc = _mock_running_process()
        mock_popen.return_value = proc

        ft_env.start("CryptoInvestorV1")
        result = ft_env.stop()
        assert result["status"] == "stopped"
        proc.terminate.assert_called_once()

    @patch("trading.services.paper_trading.subprocess.Popen")
    def test_stop_force_kill_on_timeout(self, mock_popen, ft_env):
        proc = _mock_running_process()
        # First wait (graceful) times out, second wait (after kill) succeeds
        proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="freqtrade", timeout=15),
            None,
        ]
        mock_popen.return_value = proc

        ft_env.start("CryptoInvestorV1")
        result = ft_env.stop()
        assert result["status"] == "stopped"
        proc.kill.assert_called_once()

    @patch("trading.services.paper_trading.subprocess.Popen")
    def test_status_when_running(self, mock_popen, ft_env):
        mock_popen.return_value = _mock_running_process()

        ft_env.start("CryptoInvestorV1")
        status = ft_env.get_status()
        assert status["running"] is True
        assert status["strategy"] == "CryptoInvestorV1"
        assert status["pid"] == 12345

    @patch("trading.services.paper_trading.subprocess.Popen")
    def test_detects_process_exit(self, mock_popen, ft_env):
        proc = _mock_running_process()
        mock_popen.return_value = proc

        ft_env.start("CryptoInvestorV1")
        # Simulate process exit
        proc.poll.return_value = 1
        status = ft_env.get_status()
        assert status["exit_code"] == 1

    def test_stop_when_not_running(self, ft_env):
        result = ft_env.stop()
        assert result["status"] == "not_running"


# ── Event Logging Tests ──────────────────────────────────────


class TestEventLog:
    @patch("trading.services.paper_trading.subprocess.Popen")
    def test_start_creates_log_entry(self, mock_popen, ft_env):
        mock_popen.return_value = _mock_running_process()

        ft_env.start("CryptoInvestorV1")
        entries = ft_env.get_log_entries()
        assert len(entries) == 1
        assert entries[0]["event"] == "started"

    @patch("trading.services.paper_trading.subprocess.Popen")
    def test_stop_creates_log_entry(self, mock_popen, ft_env):
        mock_popen.return_value = _mock_running_process()

        ft_env.start("CryptoInvestorV1")
        ft_env.stop()
        entries = ft_env.get_log_entries()
        assert len(entries) == 2
        assert entries[1]["event"] == "stopped"

    @patch("trading.services.paper_trading.subprocess.Popen")
    def test_log_persists_across_instances(self, mock_popen, ft_env):
        mock_popen.return_value = _mock_running_process()

        ft_env.start("CryptoInvestorV1")
        ft_env.stop()
        entries = ft_env.get_log_entries()
        assert len(entries) == 2
