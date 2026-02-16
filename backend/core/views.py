"""Core views — health, platform status, platform config."""

import logging

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class PlatformStatusView(APIView):
    def get(self, request: Request) -> Response:
        from analysis.models import BackgroundJob
        from core.platform_bridge import get_processed_dir

        # Framework status
        frameworks = _get_framework_status()

        # Data summary
        processed = get_processed_dir()
        data_files = len(list(processed.glob("*.parquet")))

        # Active jobs
        active_jobs = BackgroundJob.objects.filter(status__in=["pending", "running"]).count()

        return Response({
            "frameworks": frameworks,
            "data_files": data_files,
            "active_jobs": active_jobs,
        })


class PlatformConfigView(APIView):
    def get(self, request: Request) -> Response:
        from core.platform_bridge import get_platform_config_path

        config_path = get_platform_config_path()
        if not config_path.exists():
            return Response({"error": "platform_config.yaml not found"})
        try:
            import yaml

            with open(config_path) as f:
                return Response(yaml.safe_load(f) or {})
        except ImportError:
            return Response({"raw": config_path.read_text()[:5000]})


def _get_framework_status() -> list[dict]:
    frameworks = []

    try:
        import vectorbt as vbt
        frameworks.append({"name": "VectorBT", "installed": True, "version": vbt.__version__})
    except ImportError:
        frameworks.append({"name": "VectorBT", "installed": False, "version": None})

    try:
        import freqtrade
        ver = getattr(freqtrade, "__version__", "installed")
        frameworks.append({"name": "Freqtrade", "installed": True, "version": ver})
    except ImportError:
        frameworks.append({"name": "Freqtrade", "installed": False, "version": None})

    try:
        import nautilus_trader
        ver = getattr(nautilus_trader, "__version__", "installed")
        frameworks.append({"name": "NautilusTrader", "installed": True, "version": ver})
    except ImportError:
        frameworks.append({"name": "NautilusTrader", "installed": False, "version": None})

    try:
        import ccxt
        frameworks.append({"name": "CCXT", "installed": True, "version": ccxt.__version__})
    except ImportError:
        frameworks.append({"name": "CCXT", "installed": False, "version": None})

    try:
        import pandas as pd
        frameworks.append({"name": "Pandas", "installed": True, "version": pd.__version__})
    except ImportError:
        frameworks.append({"name": "Pandas", "installed": False, "version": None})

    return frameworks
