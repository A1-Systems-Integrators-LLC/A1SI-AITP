"""Tests for dependency validation — ensures all required frameworks are importable."""

import importlib

import pytest

# Every module listed here MUST be installed in the dev/test environment.
# If a test fails here, install the missing package — do NOT skip it.
REQUIRED_IMPORTS = [
    # Core
    "django",
    "rest_framework",
    "channels",
    "daphne",
    "ccxt",
    "httpx",
    "yaml",
    "pydantic",
    "drf_spectacular",
    # Analysis
    "pandas",
    "numpy",
    "scipy",
    "pyarrow",
    "yfinance",
    # ML
    "lightgbm",
    "sklearn",
    # Trading frameworks
    "vectorbt",
    "nautilus_trader",
    "talib",
]


@pytest.mark.parametrize("module_name", REQUIRED_IMPORTS)
def test_required_import(module_name):
    """Each required dependency must be importable — no silent skips."""
    mod = importlib.import_module(module_name)
    assert mod is not None


class TestFrameworkVersions:
    """Verify minimum versions of critical frameworks."""

    def test_lightgbm_version(self):
        import lightgbm

        major = int(lightgbm.__version__.split(".")[0])
        assert major >= 4, f"LightGBM 4.x required, got {lightgbm.__version__}"

    def test_nautilus_version(self):
        import nautilus_trader

        parts = nautilus_trader.__version__.split(".")
        assert int(parts[0]) >= 1 and int(parts[1]) >= 223, (
            f"NautilusTrader >= 1.223 required, got {nautilus_trader.__version__}"
        )

    def test_vectorbt_version(self):
        import vectorbt

        parts = vectorbt.__version__.split(".")
        assert int(parts[0]) >= 0 and int(parts[1]) >= 26, (
            f"VectorBT >= 0.26 required, got {vectorbt.__version__}"
        )

    def test_ccxt_version(self):
        import ccxt

        major = int(ccxt.__version__.split(".")[0])
        assert major >= 4, f"CCXT 4.x required, got {ccxt.__version__}"


class TestValidateDepsCommand:
    """Test the validate_deps management command."""

    def test_command_runs(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("validate_deps", stdout=out)
        output = out.getvalue()
        assert "All dependencies installed" in output

    def test_command_strict_passes(self):
        """Strict mode should not exit(1) when all deps are present."""
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        # Should not raise SystemExit
        call_command("validate_deps", "--strict", stdout=out)
