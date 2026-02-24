"""
Django settings for A1SI-AITP.

Security-hardened configuration with DRF, Channels, and session-based auth.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

TESTING = "pytest" in sys.modules or "test" in sys.argv

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BASE_DIR / ".env")

# ── Core ──────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in ("true", "1", "yes")

ENCRYPTION_KEY = os.environ.get("DJANGO_ENCRYPTION_KEY", "")

if not DEBUG and SECRET_KEY == "insecure-dev-key-change-me":
    raise ValueError("DJANGO_SECRET_KEY must be set in production")
if not DEBUG and not ENCRYPTION_KEY:
    raise ValueError("DJANGO_ENCRYPTION_KEY must be set in production")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# ── Applications ──────────────────────────────────────────────
INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "core",
    "portfolio",
    "trading",
    "market",
    "risk",
    "analysis",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CSPMiddleware",
    "core.middleware.RateLimitMiddleware",
    "core.middleware.MetricsMiddleware",
    "core.middleware.AuditMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ── Database ──────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "data" / "a1si_aitp.db",
        "OPTIONS": {
            "timeout": 30,
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Auth ──────────────────────────────────────────────────────
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Session security ─────────────────────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 3600  # 1 hour
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "__ci_sid"
SESSION_SAVE_EVERY_REQUEST = True

# ── CSRF ──────────────────────────────────────────────────────
CSRF_COOKIE_HTTPONLY = False  # Frontend reads csrftoken cookie
CSRF_FAILURE_VIEW = "core.views.csrf_failure"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://localhost:8000"
    ).split(",")
]

# ── Security headers ─────────────────────────────────────────
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Content-Security-Policy via middleware header
CSP_DEFAULT_SRC = "'self'"
CSP_SCRIPT_SRC = "'self'"
CSP_STYLE_SRC = "'self' 'unsafe-inline'"
CSP_IMG_SRC = "'self' data:"
CSP_CONNECT_SRC = "'self' ws: wss:"

if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "false").lower() == "true"

# ── DRF ───────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.exception_handler.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [] if TESTING else ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "user": "120/min",
        "anon": "30/min",
    },
}

# ── OpenAPI / drf-spectacular ─────────────────────────────────
SPECTACULAR_SETTINGS = {
    "TITLE": "A1SI-AITP API",
    "DESCRIPTION": (
        "Full-stack crypto investment platform — portfolio, trading,"
        " market analysis, risk management, backtesting, and ML."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "PREPROCESSING_HOOKS": ["core.schema.auto_tag_endpoints"],
    "SCHEMA_PATH_PREFIX": r"/api/",
    "ENUM_NAME_OVERRIDES": {},
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
    "TAGS": [
        {"name": "Auth", "description": "Authentication and session management"},
        {"name": "Portfolio", "description": "Portfolio and holdings management"},
        {"name": "Trading", "description": "Order placement, paper trading, live trading"},
        {"name": "Market", "description": "Exchange data, tickers, OHLCV, indicators"},
        {"name": "Regime", "description": "Market regime detection and strategy routing"},
        {"name": "Risk", "description": "Risk management, VaR, kill switch, alerts"},
        {"name": "Analysis", "description": "Backtesting, screening, data pipeline"},
        {"name": "ML", "description": "Machine learning model training and prediction"},
        {"name": "Scheduler", "description": "Task scheduling and automated execution"},
        {"name": "Platform", "description": "Health, status, config, metrics"},
    ],
}

# ── CORS ──────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = ["content-type", "x-csrftoken"]

# ── Channels (ASGI) ──────────────────────────────────────────
# NOTE: InMemoryChannelLayer only works within a single process. WebSocket
# messages sent in one Daphne worker will NOT reach consumers in another.
# This is acceptable for the Jetson single-process deployment target.
# For multi-process deployments, switch to channels_redis.core.RedisChannelLayer.
ASGI_APPLICATION = "config.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# ── Static files ──────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── i18n ──────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# ── App settings (used by services) ──────────────────────────
# NOTE: Legacy env-var credentials. The preferred method is the DB-backed
# ExchangeConfig model (encrypted). If both are set, the DB config takes
# priority. Run `manage.py migrate_env_credentials` to migrate, then unset
# these env vars.
EXCHANGE_ID = os.environ.get("EXCHANGE_ID", "binance")
EXCHANGE_API_KEY = os.environ.get("EXCHANGE_API_KEY", "")
EXCHANGE_API_SECRET = os.environ.get("EXCHANGE_API_SECRET", "")

if EXCHANGE_API_KEY and not TESTING:
    import warnings

    warnings.warn(
        "EXCHANGE_API_KEY env var is set. Prefer DB-backed ExchangeConfig "
        "(encrypted). Run `manage.py migrate_env_credentials` to migrate.",
        DeprecationWarning,
        stacklevel=1,
    )

MAX_JOB_WORKERS = int(os.environ.get("MAX_JOB_WORKERS", "2"))

# ── Scheduler ────────────────────────────────────────────────
SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "true").lower() in ("true", "1", "yes")
SCHEDULER_MAX_WORKERS = int(os.environ.get("SCHEDULER_MAX_WORKERS", "2"))

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")

SCHEDULED_TASKS = {
    "data_refresh_crypto": {
        "name": "Crypto Data Refresh",
        "description": "Refresh OHLCV for crypto watchlist",
        "task_type": "data_refresh",
        "interval_seconds": 3600,
        "params": {"asset_class": "crypto"},
    },
    "data_refresh_equity": {
        "name": "Equity Data Refresh",
        "description": "Refresh OHLCV for equity watchlist",
        "task_type": "data_refresh",
        "interval_seconds": 86400,
        "params": {"asset_class": "equity"},
    },
    "data_refresh_forex": {
        "name": "Forex Data Refresh",
        "description": "Refresh OHLCV for forex watchlist",
        "task_type": "data_refresh",
        "interval_seconds": 14400,
        "params": {"asset_class": "forex"},
    },
    "regime_detection": {
        "name": "Regime Detection",
        "description": "Crypto regime detection",
        "task_type": "regime_detection",
        "interval_seconds": 900,
        "params": {},
    },
    "order_sync": {
        "name": "Order Sync",
        "description": "Sync open live orders",
        "task_type": "order_sync",
        "interval_seconds": 300,
        "params": {},
    },
    "data_quality_check": {
        "name": "Data Quality Check",
        "description": "Check for stale data",
        "task_type": "data_quality",
        "interval_seconds": 3600,
        "params": {},
    },
    "news_fetch": {
        "name": "News Fetch",
        "description": "Fetch latest news",
        "task_type": "news_fetch",
        "interval_seconds": 1800,
        "params": {},
    },
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
NOTIFICATION_WEBHOOK_URL = os.environ.get("NOTIFICATION_WEBHOOK_URL", "")

# ── Login lockout ─────────────────────────────────────────────
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_WINDOW = 900  # 15 minutes
LOGIN_LOCKOUT_DURATION = 1800  # 30 minutes

# ── Rate limiting ─────────────────────────────────────────────
RATE_LIMIT_GENERAL = 120  # requests per minute
RATE_LIMIT_LOGIN = 20  # login attempts per minute

# ── Logging ───────────────────────────────────────────────────
LOG_DIR = BASE_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "INFO").upper()
_LOG_FORMAT = os.environ.get("DJANGO_LOG_FORMAT", "json" if not DEBUG else "text")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
        "json": {
            "()": "core.logging.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": _LOG_FORMAT if _LOG_FORMAT in ("json", "verbose") else "verbose",
        },
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "security.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 10,
            "formatter": "json",
        },
        "app_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "app.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 10,
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": _LOG_LEVEL,
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING"},
        "django.request": {"handlers": ["console"], "level": "WARNING"},
        "security": {"handlers": ["console", "security_file"], "level": "INFO", "propagate": False},
        "auth": {"handlers": ["console", "security_file"], "level": "INFO", "propagate": False},
        "requests": {"handlers": ["console", "app_file"], "level": "INFO", "propagate": False},
        "trading": {"handlers": ["console", "app_file"], "level": "INFO", "propagate": False},
        "risk": {"handlers": ["console", "app_file"], "level": "INFO", "propagate": False},
        "analysis": {"handlers": ["console", "app_file"], "level": "INFO", "propagate": False},
        "market": {"handlers": ["console", "app_file"], "level": "INFO", "propagate": False},
        "scheduler": {"handlers": ["console", "app_file"], "level": "INFO", "propagate": False},
    },
}
