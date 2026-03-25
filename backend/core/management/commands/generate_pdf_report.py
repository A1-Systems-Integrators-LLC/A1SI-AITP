"""Management command to generate the daily PDF intelligence report."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate a daily PDF intelligence report"

    def add_arguments(self, parser):
        parser.add_argument(
            "--portfolio-id", type=int, default=1,
            help="Portfolio ID to report on (default: 1)",
        )
        parser.add_argument(
            "--output-dir", type=str, default=None,
            help="Override output directory (default: backend/data/reports/)",
        )
        parser.add_argument(
            "--lookback-days", type=int, default=30,
            help="Historical lookback in days (default: 30)",
        )
        parser.add_argument(
            "--send-telegram", action="store_true",
            help="Send Telegram notification with report path",
        )

    def handle(self, *args, **options):
        from market.services.pdf_report import PDFReportGenerator

        self.stdout.write("Generating PDF report...")

        path = PDFReportGenerator.generate(
            portfolio_id=options["portfolio_id"],
            output_dir=options.get("output_dir"),
            lookback_days=options["lookback_days"],
        )

        size_kb = path.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(
            f"Report generated: {path} ({size_kb:.1f} KB)"
        ))

        if options["send_telegram"]:
            try:
                from core.services.notification import NotificationService

                NotificationService.send_telegram_sync(
                    f"<b>Daily PDF Report Generated</b>\n"
                    f"File: {path.name}\n"
                    f"Size: {size_kb:.1f} KB",
                )
                self.stdout.write(self.style.SUCCESS("Telegram notification sent"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Telegram failed: {e}"))
