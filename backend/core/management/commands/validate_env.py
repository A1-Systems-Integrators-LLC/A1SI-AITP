"""Validate required and recommended environment variables."""

import os
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Validate required and recommended environment variables"

    REQUIRED = [
        ("DJANGO_SECRET_KEY", "Django session signing key"),
        ("DJANGO_ENCRYPTION_KEY", "Fernet key for encrypting API credentials"),
    ]

    RECOMMENDED = [
        ("EXCHANGE_API_KEY", "Exchange API key for live trading"),
        ("NEWSAPI_KEY", "NewsAPI.org key for news/sentiment"),
        ("BACKUP_ENCRYPTION_KEY", "GPG passphrase for encrypted backups"),
        ("TELEGRAM_BOT_TOKEN", "Telegram bot token for notifications"),
    ]

    def handle(self, *args, **options):
        missing_required: list[tuple[str, str]] = []
        missing_recommended: list[tuple[str, str]] = []

        for var, desc in self.REQUIRED:
            val = os.environ.get(var, "")
            if not val or val in ("changeme", "your-secret-key-here"):
                missing_required.append((var, desc))
                self.stderr.write(self.style.ERROR(f"  MISSING: {var} — {desc}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"  OK: {var}"))

        for var, desc in self.RECOMMENDED:
            val = os.environ.get(var, "")
            if not val:
                missing_recommended.append((var, desc))
                self.stderr.write(self.style.WARNING(f"  RECOMMENDED: {var} — {desc}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"  OK: {var}"))

        if missing_required:
            self.stderr.write(
                self.style.ERROR(
                    f"\n{len(missing_required)} required variable(s) missing. "
                    "Set them in .env or environment before running in production.",
                ),
            )
            sys.exit(1)

        if missing_recommended:
            self.stderr.write(
                self.style.WARNING(
                    f"\n{len(missing_recommended)} recommended variable(s) not set. "
                    "Some features may be unavailable.",
                ),
            )
        else:
            self.stdout.write(self.style.SUCCESS("\nAll environment variables OK."))
