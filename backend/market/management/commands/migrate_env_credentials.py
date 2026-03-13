"""Migrate exchange credentials from .env to the database."""

from django.conf import settings
from django.core.management.base import BaseCommand

from market.models import ExchangeConfig


class Command(BaseCommand):
    help = "Migrate exchange credentials from .env settings to ExchangeConfig in the database"

    def handle(self, *args, **options):
        exchange_id = settings.EXCHANGE_ID
        api_key = settings.EXCHANGE_API_KEY
        api_secret = settings.EXCHANGE_API_SECRET

        if not api_key:
            self.stdout.write(
                self.style.WARNING("No EXCHANGE_API_KEY found in settings — nothing to migrate."),
            )
            return

        existing = ExchangeConfig.objects.filter(
            exchange_id=exchange_id, api_key__isnull=False,
        ).exclude(api_key="")
        if existing.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"An ExchangeConfig for '{exchange_id}'"
                    " with credentials already exists. Skipping.",
                ),
            )
            return

        config = ExchangeConfig.objects.create(
            name=f"{exchange_id.title()} (migrated from .env)",
            exchange_id=exchange_id,
            api_key=api_key,
            api_secret=api_secret,
            is_sandbox=False,
            is_default=True,
            is_active=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created ExchangeConfig #{config.pk} for '{exchange_id}' as default. "
                "You can now remove EXCHANGE_API_KEY/SECRET from your .env file.",
            ),
        )
