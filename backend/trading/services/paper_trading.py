"""Paper Trading Service — manages Freqtrade dry-run lifecycle and proxies its API."""

import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from core.platform_bridge import PROJECT_ROOT, get_freqtrade_dir

logger = logging.getLogger("paper_trading")


class PaperTradingService:
    def __init__(self, log_dir: Path | None = None) -> None:
        self._process: subprocess.Popen | None = None
        self._strategy: str = ""
        self._started_at: datetime | None = None

        ft_config = self._read_ft_config()
        api_cfg = ft_config.get("api_server", {})

        # Allow env var override for Docker (container can't reach host 127.0.0.1)
        env_url = os.environ.get("FREQTRADE_API_URL")
        if env_url:
            self._ft_api_url = env_url.rstrip("/")
        else:
            host = api_cfg.get("listen_ip_address", "127.0.0.1")
            port = api_cfg.get("listen_port", 8080)
            self._ft_api_url = f"http://{host}:{port}"
        self._ft_username = os.environ.get("FREQTRADE_USERNAME") or api_cfg.get("username", "freqtrader")
        self._ft_password = os.environ.get("FREQTRADE_PASSWORD") or api_cfg.get("password", "freqtrader")

        log_base = log_dir or (PROJECT_ROOT / "data")
        log_base.mkdir(parents=True, exist_ok=True)
        self._log_path = log_base / "paper_trading_log.jsonl"

    @staticmethod
    def _read_ft_config() -> dict:
        config_path = get_freqtrade_dir() / "config.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read Freqtrade config: {e}")
        return {}

    def _api_alive(self) -> bool:
        """Check if Freqtrade API is responding."""
        try:
            resp = httpx.get(
                f"{self._ft_api_url}/api/v1/ping", timeout=2.0,
            )
            return resp.status_code == 200
        except Exception:
            return False

    @property
    def is_running(self) -> bool:
        """Check if Freqtrade is running (managed process or external)."""
        if self._process is not None and self._process.poll() is None:
            return True
        return self._api_alive()

    def _find_freqtrade_pid(self) -> int | None:
        """Find PID of a running freqtrade process via /proc."""
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                cmdline = (pid_dir / "cmdline").read_text()
                if "freqtrade" in cmdline and "trade" in cmdline:
                    return int(pid_dir.name)
            except (OSError, ValueError):
                continue
        return None

    def start(self, strategy: str = "CryptoInvestorV1") -> dict:
        if self.is_running:
            return {
                "status": "already_running",
                "strategy": self._strategy or strategy,
                "pid": self._process.pid if self._process else self._find_freqtrade_pid(),
            }

        ft_config = get_freqtrade_dir() / "config.json"
        strat_path = get_freqtrade_dir() / "user_data" / "strategies"

        if not ft_config.exists():
            return {"status": "error", "error": "Freqtrade config.json not found"}

        cmd = [
            sys.executable,
            "-m",
            "freqtrade",
            "trade",
            "--config",
            str(ft_config),
            "--strategy",
            strategy,
            "--strategy-path",
            str(strat_path),
        ]
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(PROJECT_ROOT),
            )
        except FileNotFoundError:
            return {"status": "error", "error": "Python or Freqtrade not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

        self._strategy = strategy
        self._started_at = datetime.now(timezone.utc)
        self._log_event("started", {"strategy": strategy, "pid": self._process.pid})
        logger.info(f"Paper trading started: {strategy} (PID {self._process.pid})")
        return {
            "status": "started",
            "strategy": strategy,
            "pid": self._process.pid,
            "started_at": self._started_at.isoformat(),
        }

    def stop(self) -> dict:
        if self._process is not None and self._process.poll() is None:
            pid = self._process.pid
            strategy = self._strategy
            self._process.terminate()
            try:
                self._process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                logger.warning(f"Freqtrade PID {pid} did not stop gracefully, killing")
                self._process.kill()
                self._process.wait(timeout=5)
            self._process = None
        elif self._api_alive():
            pid = self._find_freqtrade_pid()
            strategy = self._strategy
            if pid:
                os.kill(pid, signal.SIGTERM)
                logger.info(f"Sent SIGTERM to external Freqtrade PID {pid}")
            else:
                return {"status": "error", "error": "API alive but PID not found"}
        else:
            return {"status": "not_running"}

        self._log_event("stopped", {"pid": pid, "strategy": strategy})
        logger.info(f"Paper trading stopped: {strategy} (PID {pid})")
        return {"status": "stopped", "pid": pid}

    def get_status(self) -> dict:
        # Check managed process first
        if self._process is not None:
            if self._process.poll() is None:
                uptime = (datetime.now(timezone.utc) - self._started_at).total_seconds()
                return {
                    "running": True,
                    "strategy": self._strategy,
                    "pid": self._process.pid,
                    "started_at": self._started_at.isoformat(),
                    "uptime_seconds": round(uptime),
                }
            exit_code = self._process.poll()
            self._process = None
            return {
                "running": False,
                "strategy": self._strategy or None,
                "uptime_seconds": 0,
                "exit_code": exit_code,
            }

        # No managed process — probe Freqtrade API for external process
        if self._api_alive():
            try:
                auth = httpx.BasicAuth(self._ft_username, self._ft_password)
                resp = httpx.get(
                    f"{self._ft_api_url}/api/v1/show_config",
                    auth=auth,
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    cfg = resp.json()
                    return {
                        "running": True,
                        "strategy": cfg.get("strategy", "unknown"),
                        "pid": self._find_freqtrade_pid(),
                        "exchange": cfg.get("exchange"),
                        "dry_run": cfg.get("dry_run"),
                        "state": cfg.get("state"),
                        "uptime_seconds": 0,
                    }
            except Exception:
                pass

        return {
            "running": False,
            "strategy": self._strategy or None,
            "uptime_seconds": 0,
            "exit_code": None,
        }

    async def _ft_get(self, endpoint: str) -> Any:
        """Call Freqtrade REST API using HTTP Basic auth."""
        try:
            auth = httpx.BasicAuth(self._ft_username, self._ft_password)
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._ft_api_url}/api/v1/{endpoint}",
                    auth=auth,
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    return resp.json()
        except httpx.ConnectError:
            logger.debug(f"Freqtrade API not reachable for {endpoint}")
        except Exception as e:
            logger.debug(f"Freqtrade API error ({endpoint}): {e}")
        return None

    async def get_open_trades(self) -> list[dict]:
        data = await self._ft_get("status")
        return data if isinstance(data, list) else []

    async def get_trade_history(self, limit: int = 50) -> list[dict]:
        data = await self._ft_get(f"trades?limit={limit}")
        if isinstance(data, dict):
            return data.get("trades", [])
        return []

    async def get_profit(self) -> dict:
        data = await self._ft_get("profit")
        return data if isinstance(data, dict) else {}

    async def get_performance(self) -> list[dict]:
        data = await self._ft_get("performance")
        return data if isinstance(data, list) else []

    async def get_balance(self) -> dict:
        data = await self._ft_get("balance")
        return data if isinstance(data, dict) else {}

    def _log_event(self, event: str, data: dict | None = None) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **(data or {}),
        }
        try:
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            logger.warning(f"Failed to write log: {e}")

    def get_log_entries(self, limit: int = 100) -> list[dict]:
        if not self._log_path.exists():
            return []
        entries = []
        try:
            with open(self._log_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        with contextlib.suppress(json.JSONDecodeError):
                            entries.append(json.loads(line))
        except OSError:
            return []
        return entries[-limit:]
