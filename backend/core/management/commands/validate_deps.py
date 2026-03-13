"""Management command to validate all required framework dependencies are installed."""

import importlib
import sys

from django.core.management.base import BaseCommand


REQUIRED_DEPS = {
    "core": [
        ("django", "Django"),
        ("rest_framework", "Django REST Framework"),
        ("channels", "Django Channels"),
        ("daphne", "Daphne"),
        ("ccxt", "CCXT"),
        ("httpx", "HTTPX"),
        ("yaml", "PyYAML"),
        ("pydantic", "Pydantic"),
        ("drf_spectacular", "drf-spectacular"),
    ],
    "analysis": [
        ("pandas", "Pandas"),
        ("numpy", "NumPy"),
        ("scipy", "SciPy"),
        ("pyarrow", "PyArrow"),
        ("yfinance", "yfinance"),
    ],
    "ml": [
        ("lightgbm", "LightGBM"),
        ("sklearn", "scikit-learn"),
    ],
    "trading": [
        ("vectorbt", "VectorBT"),
        ("nautilus_trader", "NautilusTrader"),
        ("talib", "TA-Lib"),
    ],
}


class Command(BaseCommand):
    help = "Validate all required framework dependencies are installed"

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with code 1 if any dependency is missing",
        )

    def handle(self, *args, **options):
        missing = []
        for group, deps in REQUIRED_DEPS.items():
            self.stdout.write(f"\n[{group}]")
            for module_name, display_name in deps:
                try:
                    mod = importlib.import_module(module_name)
                    version = getattr(mod, "__version__", "installed")
                    self.stdout.write(f"  ✓ {display_name} ({version})")
                except ImportError:
                    self.stdout.write(self.style.ERROR(f"  ✗ {display_name} — NOT INSTALLED"))
                    missing.append(display_name)

        self.stdout.write("")
        if missing:
            self.stdout.write(
                self.style.ERROR(f"MISSING {len(missing)} dependencies: {', '.join(missing)}")
            )
            if options["strict"]:
                sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("All dependencies installed."))
