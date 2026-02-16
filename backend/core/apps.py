from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _set_sqlite_pragmas(sender, connection, **kwargs):
    """Enable WAL mode and tune SQLite for performance."""
    if connection.vendor == "sqlite":
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")


class CoreConfig(AppConfig):
    name = "core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        connection_created.connect(_set_sqlite_pragmas)
