"""Django settings for A1SI-AITP.

Security-hardened configuration with DRF, Channels, and session-based auth.
"""

import os
import shutil
import sys
from pathlib import Path

TESTING = "pytest" in sys.modules or "test" in sys.argv

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

# Prefer Doppler for secrets injection; fall back to .env files when Doppler is
# not available (e.g. bare-metal dev without the CLI installed).
if not shutil.which("doppler") or os.environ.get("DOPPLER_DISABLE") == "1":
    from dotenv import load_dotenv

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
    "django.middleware.gzip.GZipMiddleware",
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
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "a1si_aitp"),
        "USER": os.environ.get("POSTGRES_USER", "a1si"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 0 if TESTING else 600,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "connect_timeout": 10,
        },
    },
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
SESSION_COOKIE_AGE = 1800  # 30 minutes (financial platform — minimize exposure window)
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
        "CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://localhost:8000",
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
CSP_STYLE_SRC = "'self'"
CSP_IMG_SRC = "'self' data:"
CSP_CONNECT_SRC = "'self' ws: wss:"
CSP_OBJECT_SRC = "'none'"
CSP_BASE_URI = "'self'"
CSP_FORM_ACTION = "'self'"
CSP_FRAME_ANCESTORS = "'none'"

SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"

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
# This is acceptable for the single-process desktop deployment target.
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
EXCHANGE_ID = os.environ.get("EXCHANGE_ID", "kraken")
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

# Job runner thread pool size. Default was 2, which caused thread starvation
# when multiple long-running tasks (ML training, backtests) ran concurrently,
# blocking critical safety tasks (risk monitoring, order sync).
MAX_JOB_WORKERS = int(os.environ.get("MAX_JOB_WORKERS", "4"))

ORDER_SYNC_TIMEOUT_HOURS = int(os.environ.get("ORDER_SYNC_TIMEOUT_HOURS", "24"))

# ── Freqtrade Instances ─────────────────────────────────────
# 2026-05-22 consolidation: cut 4 strategies after 6 weeks of paper trading.
# Kept: MomentumScalper15m (3-0 wins), TrendReversal (first close +$0.14),
# SentimentEventTrader (3-entry-path fix on 2026-04-15, never trialed).
# Disabled: BMR (0-1), CryptoInvestorV1 (0-3), VolatilityBreakout (1-3 losing),
# GridDCA (0-7). Entries kept (not deleted) so existing tests still resolve.
# Reactivate by flipping "enabled" to True AND re-adding the service in
# docker-compose.prod.yml.
FREQTRADE_INSTANCES = [
    {
        "name": "BollingerMeanReversion",
        "config": "config_bmr.json",
        "port": 4183,
        "url": os.environ.get("FREQTRADE_BMR_API_URL", ""),
        "enabled": False,
    },
    {
        "name": "CryptoInvestorV1",
        "config": "config.json",
        "port": 4180,
        "url": os.environ.get("FREQTRADE_CIV1_API_URL", ""),
        "enabled": False,
    },
    {
        "name": "VolatilityBreakout",
        "config": "config_vb.json",
        "port": 4184,
        "url": os.environ.get("FREQTRADE_VB_API_URL", ""),
        "enabled": False,
    },
    {
        "name": "MomentumScalper15m",
        "config": "config_scalp.json",
        "port": 4187,
        "url": os.environ.get("FREQTRADE_SCALP_API_URL", "http://freqtrade-scalp:4187"),
        "dry_run_wallet": 200,
        "enabled": True,
    },
    {
        "name": "GridDCA",
        "config": "config_grid.json",
        "port": 4186,
        "url": os.environ.get("FREQTRADE_GRID_API_URL", ""),
        "enabled": False,
    },
    {
        "name": "SentimentEventTrader",
        "config": "config_sentiment.json",
        "port": 4188,
        "url": os.environ.get("FREQTRADE_SENTIMENT_API_URL", "http://freqtrade-sentiment:4188"),
        "dry_run_wallet": 200,
        "enabled": True,
    },
    {
        "name": "TrendReversal",
        "config": "config_reversal.json",
        "port": 4189,
        "url": os.environ.get("FREQTRADE_REVERSAL_API_URL", "http://freqtrade-reversal:4189"),
        "dry_run_wallet": 200,
        "enabled": True,
    },
]

# ── Scheduler ────────────────────────────────────────────────
SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "true").lower() in ("true", "1", "yes")
SCHEDULER_MAX_WORKERS = int(os.environ.get("SCHEDULER_MAX_WORKERS", "2"))

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")

# ── Internal API authentication ──────────────────────────────
# HMAC secret for Freqtrade/NautilusTrader → Django internal API calls.
# When set, internal endpoints verify X-Internal-Signature header.
# When empty, internal endpoints accept requests from INTERNAL_API_ALLOWED_IPS only.
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "")
INTERNAL_API_ALLOWED_IPS = os.environ.get(
    "INTERNAL_API_ALLOWED_IPS", "127.0.0.1,::1,172.17.0.1",
).split(",")

# ── Scheduled tasks ─────────────────────────────────────────
# 2026-05-22 consolidation: cut from 38 tasks (~58/hour, thundering-herd
# every :00 and :30) to 22 tasks (~10/hour, all cron-scheduled with staggered
# minute offsets so no two tasks share a minute boundary).
#
# Cut categories:
#   - Asset classes we don't trade (equity, forex): 9 tasks removed
#   - Unused frameworks (VectorBT screens, NautilusTrader/HFT backtests): 3 removed
#   - Redundant / questionable (order_sync, daily_report dupe, autonomous_check,
#     adaptive_weighting): 4 removed
#
# Removed task IDs (executors remain in task_registry for manual triggering):
#   data_refresh_equity, data_refresh_forex, data_refresh_forex_4h,
#   vbt_screen_crypto, vbt_screen_forex, vbt_screen_equity,
#   market_scan_forex, forex_paper_trading,
#   nautilus_backtest_crypto, nautilus_backtest_equity, nautilus_backtest_forex,
#   hft_backtest, order_sync, daily_report, autonomous_check, adaptive_weighting
SCHEDULED_TASKS = {
    # ── Core crypto data & analysis (hourly, staggered) ──────────────────────
    "data_refresh_crypto": {
        "name": "Crypto Data Refresh",
        "description": "Refresh OHLCV for crypto watchlist",
        "task_type": "data_refresh",
        "cron_schedule": "13 * * * *",
        "params": {"asset_class": "crypto"},
    },
    "data_refresh_crypto_4h": {
        "name": "Crypto 4h Data Refresh",
        "description": "Refresh 4h OHLCV for crypto watchlist",
        "task_type": "data_refresh",
        "cron_schedule": "8 */4 * * *",
        "params": {"asset_class": "crypto", "timeframe": "4h"},
    },
    "regime_detection": {
        "name": "Regime Detection",
        "description": "Crypto regime detection",
        "task_type": "regime_detection",
        "cron_schedule": "23 * * * *",
        "params": {},
    },
    "data_quality_check": {
        "name": "Data Quality Check",
        "description": "Check for stale data",
        "task_type": "data_quality",
        "cron_schedule": "43 * * * *",
        "params": {},
    },
    "news_fetch": {
        "name": "News Fetch",
        "description": "Fetch latest news",
        "task_type": "news_fetch",
        "cron_schedule": "33 * * * *",
        "params": {},
    },
    # ── Risk & trading (high cadence) ────────────────────────────────────────
    "risk_monitoring": {
        "name": "Risk Monitoring",
        "description": "Periodic risk check across portfolios",
        "task_type": "risk_monitoring",
        "cron_schedule": "*/5 * * * *",
        "params": {},
    },
    "market_scan_crypto": {
        "name": "Crypto Market Scanner",
        "description": "Scan crypto pairs for trading opportunities",
        "task_type": "market_scan",
        "cron_schedule": "2,17,32,47 * * * *",
        "params": {"asset_class": "crypto", "timeframe": "1h"},
    },
    "strategy_orchestration": {
        "name": "Strategy Orchestration",
        "description": "Evaluate regime-strategy alignment, pause/resume strategies",
        "task_type": "strategy_orchestration",
        "cron_schedule": "7,22,37,52 * * * *",
        "params": {},
    },
    "signal_feedback": {
        "name": "Signal Feedback",
        "description": "Backfill signal attribution outcomes and compute source accuracy",
        "task_type": "signal_feedback",
        "cron_schedule": "53 * * * *",
        "params": {},
    },
    # ── Sentiment & external data (4h, staggered) ────────────────────────────
    "economic_calendar": {
        "name": "Economic Calendar Check",
        "description": "Check for upcoming high-impact economic events",
        "task_type": "economic_calendar",
        "cron_schedule": "18 */4 * * *",
        "params": {},
    },
    "macro_data_refresh": {
        "name": "FRED Macro Data Refresh",
        "description": "Fetch Fed Funds, yield curve, VIX, DXY from FRED",
        "task_type": "macro_data_refresh",
        "cron_schedule": "28 */4 * * *",
        "params": {},
    },
    "reddit_sentiment_refresh": {
        "name": "Reddit Sentiment Refresh",
        "description": "Scrape crypto subreddits for sentiment scoring",
        "task_type": "reddit_sentiment_refresh",
        "cron_schedule": "38 */4 * * *",
        "params": {},
    },
    "coingecko_trending_refresh": {
        "name": "CoinGecko Trending Refresh",
        "description": "Fetch trending coins and DeFi market data",
        "task_type": "coingecko_trending_refresh",
        "cron_schedule": "48 */4 * * *",
        "params": {},
    },
    "fear_greed_refresh": {
        "name": "Fear & Greed Index Refresh",
        "description": "Fetch Fear & Greed Index for contrarian crypto signals",
        "task_type": "fear_greed_refresh",
        "cron_schedule": "58 */4 * * *",
        "params": {},
    },
    "ml_predict": {
        "name": "ML Predictions",
        "description": "Generate ML predictions for watchlist symbols",
        "task_type": "ml_predict",
        "cron_schedule": "5 */4 * * *",
        "params": {"asset_class": "crypto"},
    },
    # ── Lower cadence ────────────────────────────────────────────────────────
    "funding_rate_refresh": {
        "name": "Funding Rate Refresh",
        "description": "Fetch latest funding rates for crypto pairs",
        "task_type": "funding_rate_refresh",
        "cron_schedule": "15 */8 * * *",
        "params": {"asset_class": "crypto"},
    },
    # ── Daily housekeeping ───────────────────────────────────────────────────
    "daily_risk_reset": {
        "name": "Daily Risk Reset",
        "description": "Reset daily P&L counters at midnight UTC for all portfolios",
        "task_type": "daily_risk_reset",
        "cron_schedule": "0 0 * * *",
        "params": {},
    },
    "ml_training": {
        "name": "ML Model Training",
        "description": "Daily LightGBM model training on top crypto symbols",
        "task_type": "ml_training",
        "cron_schedule": "0 6 * * *",
        "params": {
            "symbols": [
                "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
                "BNB/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT",
            ],
            "timeframe": "1h",
        },
    },
    "ml_feedback": {
        "name": "ML Feedback",
        "description": "Backfill prediction outcomes and update model performance",
        "task_type": "ml_feedback",
        "cron_schedule": "15 7 * * *",
        "params": {},
    },
    "db_maintenance": {
        "name": "Database Maintenance",
        "description": "PostgreSQL health check and maintenance",
        "task_type": "db_maintenance",
        "cron_schedule": "30 3 * * *",
        "params": {},
    },
    "pdf_report_daily": {
        "name": "Daily PDF Report",
        "description": "Generate daily PDF intelligence report at 5 PM Eastern",
        "task_type": "pdf_report",
        "cron_schedule": "0 17 * * *|US/Eastern",
        "params": {},
    },
    "db_backup_daily": {
        "name": "Daily Database Backup",
        "description": "PostgreSQL backup with compression at 2 AM Eastern",
        "task_type": "db_backup",
        "cron_schedule": "0 2 * * *|US/Eastern",
        "params": {},
    },
}

# ── Workflow templates ────────────────────────────────────────
WORKFLOW_TEMPLATES: dict = {
    "research_pipeline": {
        "name": "Research Pipeline",
        "description": "Screen for opportunities after data refresh",
        "asset_class": "crypto",
        "steps": [
            {"order": 1, "name": "Refresh Data", "step_type": "data_refresh"},
            {"order": 2, "name": "VBT Screen", "step_type": "vbt_screen"},
            {"order": 3, "name": "Evaluate Alerts", "step_type": "alert_evaluate"},
        ],
    },
    "signal_pipeline": {
        "name": "Signal Pipeline",
        "description": "Alert on extreme sentiment signals",
        "asset_class": "crypto",
        "steps": [
            {"order": 1, "name": "Fetch News", "step_type": "news_fetch"},
            {"order": 2, "name": "Aggregate Sentiment", "step_type": "sentiment_aggregate"},
            {"order": 3, "name": "Evaluate Alerts", "step_type": "alert_evaluate"},
        ],
    },
    "risk_pipeline": {
        "name": "Risk Pipeline",
        "description": "Alert on regime changes",
        "asset_class": "crypto",
        "steps": [
            {"order": 1, "name": "Detect Regimes", "step_type": "regime_detection"},
            {"order": 2, "name": "Strategy Recommend", "step_type": "strategy_recommend"},
            {"order": 3, "name": "Evaluate Alerts", "step_type": "alert_evaluate"},
        ],
    },
    "full_analysis_pipeline": {
        "name": "Full Analysis Pipeline",
        "description": "Complete analysis chain: data, regime, sentiment, composite, alerts",
        "asset_class": "crypto",
        "schedule_interval_seconds": 21600,
        "schedule_enabled": True,
        "steps": [
            {"order": 1, "name": "Refresh Data", "step_type": "data_refresh"},
            {"order": 2, "name": "Detect Regimes", "step_type": "regime_detection"},
            {"order": 3, "name": "Aggregate Sentiment", "step_type": "sentiment_aggregate"},
            {"order": 4, "name": "Composite Score", "step_type": "composite_score"},
            {"order": 5, "name": "Evaluate Alerts", "step_type": "alert_evaluate"},
        ],
    },
    "ml_training_pipeline": {
        "name": "ML Training Pipeline",
        "description": "Weekly ML model training: refresh data, train models, evaluate",
        "asset_class": "crypto",
        "schedule_interval_seconds": 604800,
        "schedule_enabled": True,
        "steps": [
            {"order": 1, "name": "Refresh Data", "step_type": "data_refresh"},
            {"order": 2, "name": "Train ML Model", "step_type": "ml_training"},
            {"order": 3, "name": "Evaluate Alerts", "step_type": "alert_evaluate"},
        ],
    },
}

FREQTRADE_API_URL = os.environ.get("FREQTRADE_API_URL", "")
FREQTRADE_BMR_API_URL = os.environ.get("FREQTRADE_BMR_API_URL", "")
FREQTRADE_VB_API_URL = os.environ.get("FREQTRADE_VB_API_URL", "")

FREQTRADE_USERNAME = os.environ.get("FREQTRADE_USERNAME", "")
FREQTRADE_PASSWORD = os.environ.get("FREQTRADE_PASSWORD", "")

if not DEBUG and not FREQTRADE_PASSWORD:
    import warnings

    warnings.warn(
        "FREQTRADE_PASSWORD is not set — Freqtrade API calls will fail. "
        "Set FREQTRADE_PASSWORD in Doppler or .env.",
        stacklevel=1,
    )

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
