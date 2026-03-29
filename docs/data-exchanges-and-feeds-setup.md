# Data Exchanges & Feeds Setup Guide

Complete guide to configuring all data sources, exchange connections, and market feeds for the A1SI-AITP platform.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Secrets Management (Doppler)](#secrets-management-doppler)
3. [Exchange Setup — Kraken (Primary)](#exchange-setup--kraken-primary)
4. [Exchange Setup — Binance](#exchange-setup--binance)
5. [Exchange Setup — Bybit](#exchange-setup--bybit)
6. [Exchange Setup — Coinbase](#exchange-setup--coinbase)
7. [Exchange Setup — KuCoin](#exchange-setup--kucoin)
8. [Yahoo Finance (Equities & Forex)](#yahoo-finance-equities--forex)
9. [FRED Economic Data](#fred-economic-data)
10. [News & Sentiment Feeds](#news--sentiment-feeds)
11. [Alternative Data Sources](#alternative-data-sources)
12. [Data Pipeline Operations](#data-pipeline-operations)
13. [Framework Containers](#framework-containers)
14. [Security Best Practices](#security-best-practices)
15. [Verification & Troubleshooting](#verification--troubleshooting)

---

## Prerequisites

- Docker and Docker Compose installed
- Doppler CLI installed and authenticated (`doppler --version`)
- Project linked to Doppler: `make doppler-setup`

### Available CLIs

| CLI Tool | Purpose | Install |
|----------|---------|---------|
| `doppler` | Secrets management | `brew install dopplerhq/cli/doppler` |
| `docker compose` | Container orchestration | Bundled with Docker Desktop |
| `ccxt` | Exchange connectivity (Python) | Installed in backend container |
| `freqtrade` | Crypto trading CLI | `freqtradeorg/freqtrade:stable` Docker image |
| `yfinance` | Equity/forex data (Python) | Installed in backend container |
| `python run.py` | Platform orchestrator | Project CLI (runs in venv or container) |

---

## Secrets Management (Doppler)

All API keys and credentials are managed via Doppler. **Never put secrets in `.env` files or code.**

### Initial Setup

```bash
# Install Doppler CLI
brew install dopplerhq/cli/doppler

# Authenticate (one-time)
doppler login

# Link project
doppler setup --project aitp --config dev --no-interactive

# Verify
doppler secrets --only-names
```

### Setting Secrets

```bash
# Set a single secret
doppler secrets set KRAKEN_API_KEY="your-api-key" --project aitp --config dev

# Set multiple secrets at once
doppler secrets set \
  KRAKEN_API_KEY="your-key" \
  KRAKEN_SECRET="your-secret" \
  --project aitp --config dev

# View a secret value
doppler secrets get KRAKEN_API_KEY --plain

# Run any command with secrets injected
doppler run -- make dev
doppler run -- docker compose up -d
```

### Environments

| Config | Purpose | Usage |
|--------|---------|-------|
| `dev` | Local development | `doppler run --config dev -- ...` |
| `stg` | Staging/testing | `doppler run --config stg -- ...` |
| `prd` | Production trading | `doppler run --config prd -- ...` |

---

## Exchange Setup — Kraken (Primary)

Kraken is the primary exchange for crypto trading and market data.

### 1. Create API Key

1. Log in to [Kraken](https://www.kraken.com)
2. Navigate to **Security** > **API** > **Add Key**
3. Configure permissions:
   - **Query Funds** — Required for balance checks
   - **Query Open Orders & Trades** — Required for order monitoring
   - **Query Closed Orders & Trades** — Required for trade history
   - **Create & Modify Orders** — Required for live trading (skip for data-only)
   - **Cancel/Close Orders** — Required for live trading
4. Set **Nonce Window** to at least `5000` (recommended for API stability)
5. Optionally restrict to your IP address for security
6. Copy the API Key and Private Key

### 2. Store in Doppler

```bash
doppler secrets set \
  KRAKEN_API_KEY="your-kraken-api-key" \
  KRAKEN_SECRET="your-kraken-private-key" \
  --project aitp --config dev
```

### 3. Verify Connection

```bash
# Via platform CLI
doppler run -- python run.py data download --symbols BTC/USDT --exchange kraken --timeframes 1h

# Via Docker
doppler run -- docker compose exec backend python -c "
from market.services.exchange import ExchangeService
import asyncio
svc = ExchangeService('kraken')
print(asyncio.run(svc.fetch_ticker('BTC/USDT')))
"
```

### 4. Kraken-Specific Notes

- **Rate limits**: 15 calls/minute for public, 20 calls/minute for private endpoints
- **Sandbox mode**: Set `is_sandbox=true` in ExchangeConfig to use Kraken's demo environment
- **Supported pairs**: All USDT pairs (BTC, ETH, SOL, XRP, DOGE, LTC, etc.)
- **Trading mode**: Spot only (no margin/futures in current config)
- **Fee tier**: 0.16% maker / 0.26% taker (default; volume discounts available)

### Data Available from Kraken

| Data Type | Method | Refresh Rate |
|-----------|--------|-------------|
| OHLCV candles | CCXT `fetch_ohlcv()` | Every 30 min |
| Ticker prices | CCXT `fetch_ticker()` | Real-time |
| Order book | CCXT `fetch_order_book()` | On demand |
| Trade history | CCXT `fetch_trades()` | On demand |
| Funding rates | Via Bybit adapter (Kraken Futures) | Every 8 hours |

---

## Exchange Setup — Binance

Binance is an optional secondary exchange (geo-blocked in some US locations; use Binance.US if needed).

### 1. Create API Key

1. Log in to [Binance](https://www.binance.com) or [Binance.US](https://www.binance.us)
2. Navigate to **API Management**
3. Create a new API key with:
   - **Enable Reading** — Required
   - **Enable Spot & Margin Trading** — For live trading only
4. Restrict to your IP address

### 2. Store in Doppler

```bash
doppler secrets set \
  BINANCE_API_KEY="your-binance-api-key" \
  BINANCE_SECRET="your-binance-secret" \
  --project aitp --config dev
```

### 3. Notes

- The platform config defaults `EXCHANGE_ID=kraken` — Binance is used when specified per-symbol
- CryptoInvestorV1 strategy uses `kraken` exchange, same as all other strategies
- Rate limit: 1200 requests/minute (weight-based)

---

## Exchange Setup — Bybit

Bybit provides funding rate data and serves as a tertiary exchange.

### 1. Create API Key

1. Log in to [Bybit](https://www.bybit.com)
2. Navigate to **API Management**
3. Create a key with read permissions

### 2. Store in Doppler

```bash
doppler secrets set \
  BYBIT_API_KEY="your-bybit-api-key" \
  BYBIT_SECRET="your-bybit-secret" \
  --project aitp --config dev
```

---

## Exchange Setup — Coinbase

Coinbase is an optional exchange, primarily useful for US-based users.

### 1. Create Account & API Key

1. Go to [Coinbase](https://www.coinbase.com/signup) and register with email
2. Verify identity with government ID
3. Enable two-factor authentication (2FA)
4. Navigate to **Settings > API** or use the Coinbase Developer Platform
5. Click **New API Key**
6. Select the accounts you want to grant access to
7. Set permissions:
   - **wallet:accounts:read** — Required for balance checks
   - **wallet:trades:create** — For live trading only
8. Complete 2FA verification
9. Copy the API Key and API Secret

### 2. Store in Doppler

```bash
doppler secrets set \
  COINBASE_API_KEY="your-coinbase-api-key" \
  COINBASE_SECRET="your-coinbase-secret" \
  --project aitp --config dev
```

---

## Exchange Setup — KuCoin

KuCoin is an optional exchange. Note that KuCoin requires a **passphrase** in addition to the API key and secret.

### 1. Create Account & API Key

1. Go to [KuCoin](https://www.kucoin.com/ucenter/signup) and register with email or phone
2. Complete KYC verification
3. Enable 2FA
4. Set a trading password — you will need this as the API passphrase
5. Navigate to **Account Security > API Management**
6. Click **Create API**
7. Enter your trading password
8. Set a name and passphrase — **save this passphrase, you will need it**
9. Set permissions:
   - **General** — Required
   - **Trade** — For live trading only
10. Set IP restriction if possible
11. Copy the API Key, Secret, and Passphrase

### 2. Store in Doppler

```bash
doppler secrets set \
  KUCOIN_API_KEY="your-kucoin-api-key" \
  KUCOIN_SECRET="your-kucoin-secret" \
  KUCOIN_PASSPHRASE="your-kucoin-passphrase" \
  --project aitp --config dev
```

---

## Yahoo Finance (Equities & Forex)

Yahoo Finance provides free equity and forex data via the `yfinance` Python library. **No API key required.**

### How It Works

- **Library**: `yfinance` (installed in backend container)
- **Authentication**: None needed — free public data
- **Asset classes**: US equities, ETFs, indices, forex pairs
- **Adapter**: `common/data_pipeline/yfinance_adapter.py`

### Symbol Format Conversion

| Platform Format | yfinance Format | Type |
|-----------------|----------------|------|
| `AAPL/USD` | `AAPL` | Equity |
| `SPY/USD` | `SPY` | ETF |
| `^GSPC/USD` | `^GSPC` | Index |
| `EUR/USD` | `EURUSD=X` | Forex |
| `GBP/USD` | `GBPUSD=X` | Forex |

### Timeframe Limits

| Timeframe | Max History | Notes |
|-----------|-------------|-------|
| 1m | 7 days | Very short window |
| 5m, 15m | 60 days | |
| 1h | 730 days | |
| 4h | 730 days | Fetches 1h and resamples |
| 1d | Unlimited | Full history |

### Verify Connection

```bash
doppler run -- docker compose exec backend python -c "
from market.services.yfinance_service import YFinanceService
import asyncio
svc = YFinanceService()
print(asyncio.run(svc.fetch_ticker('AAPL/USD', 'equity')))
"
```

### Supported Watchlists

**Equities** (90+ symbols): AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, V, MA, UNH, JNJ, LLY, SPY, QQQ, IWM, GLD, TLT, and many more.

**Forex** (40+ pairs): EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, NZD/USD, USD/CAD, plus crosses and emerging market pairs.

---

## FRED Economic Data

The Federal Reserve Economic Data (FRED) API provides macroeconomic indicators.

### 1. Get API Key

1. Go to [FRED API Keys](https://fred.stlouisfed.org/docs/api/api_key.html)
2. Create a free account
3. Request an API key (instant approval)

### 2. Store in Doppler

```bash
doppler secrets set FRED_API_KEY="your-fred-api-key" --project aitp --config dev
```

### 3. Data Series Tracked

| Series | Description | Impact |
|--------|-------------|--------|
| DFF | Federal Funds Rate | Monetary policy signal |
| T10Y2Y | 10Y-2Y Yield Curve | Recession indicator |
| VIXCLS | VIX Volatility Index | Market fear gauge |
| DTWEXBGS | Trade-Weighted USD | Dollar strength proxy |

### 4. Composite Macro Score

The platform computes a 0-100 macro score combining all four indicators, used for:
- Position sizing adjustments
- Regime detection
- Risk management overlay

Refresh: Every 4 hours. Cache TTL: 4 hours.

---

## News & Sentiment Feeds

### RSS Feeds (Free, No API Key)

Always active. Sources by asset class:

| Asset Class | Sources |
|-------------|---------|
| Crypto | CoinDesk, CoinTelegraph, Decrypt |
| Equity | Yahoo Finance, MarketWatch |
| Forex | DailyFX, ForexFactory |

Refresh: Every 30 minutes.

### NewsAPI (Optional)

For broader news coverage beyond RSS feeds.

1. Sign up at [NewsAPI.org](https://newsapi.org)
2. Free tier: 100 requests/day
3. Store key:

```bash
doppler secrets set NEWSAPI_KEY="your-newsapi-key" --project aitp --config dev
```

### Reddit Sentiment (Free, No API Key)

- Scrapes public Reddit JSON API
- Subreddits: r/CryptoCurrency, r/Bitcoin, r/ethereum
- Keyword-based bullish/bearish scoring (-1 to +1)
- Refresh: Every 30 minutes. Cache: 15 minutes.

---

## Alternative Data Sources

All free, no API keys required.

| Source | Data | Refresh | Cache |
|--------|------|---------|-------|
| [CoinGecko](https://api.coingecko.com) | BTC dominance, trending coins, DeFi data | 30 min | 5 min |
| [Fear & Greed Index](https://alternative.me/crypto/fear-and-greed-index/) | Crypto market sentiment (0-100) | 1 hour | 1 hour |
| [DefiLlama](https://api.llama.fi) | Total Value Locked by chain | 30 min | 1 hour |
| [Blockchain.info](https://blockchain.info) | BTC hash rate, mempool, TX count | On demand | 1 hour |
| [ForexFactory](https://nfs.faireconomy.media/ff_calendar_thisweek.json) | Economic calendar (FOMC, NFP, CPI) | 4 hours | 4 hours |

---

## Data Pipeline Operations

### Download Market Data

```bash
# Download all crypto watchlist data
doppler run -- python run.py data download --asset-class crypto --timeframes 1h,4h,1d

# Download specific symbols
doppler run -- python run.py data download --symbols BTC/USDT,ETH/USDT --timeframes 1h

# Download equity data (uses yfinance, no key needed)
doppler run -- python run.py data download --asset-class equity --timeframes 1d

# Download forex data
doppler run -- python run.py data download --asset-class forex --timeframes 1h,4h

# Generate synthetic test data (no exchange needed)
doppler run -- python run.py data generate-sample

# List all available data files
doppler run -- python run.py data list
```

### Docker Operations

```bash
# Download data via Docker backend container
doppler run -- docker compose exec backend python run.py data download

# Check data quality
doppler run -- docker compose exec backend python manage.py pilot_preflight
```

### Scheduled Data Refresh

The backend scheduler automatically refreshes data:

| Task | Asset Class | Interval | Timeframes |
|------|-------------|----------|-----------|
| `data_refresh_crypto` | Crypto | 30 min | 1h, 4h, 1d |
| `data_refresh_equity` | Equity | 24 hours | 1h, 1d |
| `data_refresh_forex` | Forex | 1 hour | 1h, 4h, 1d |
| `funding_rate_refresh` | Crypto | 8 hours | N/A |
| `fear_greed_refresh` | Crypto | 1 hour | N/A |
| `reddit_sentiment_refresh` | Crypto | 30 min | N/A |
| `coingecko_trending_refresh` | Crypto | 30 min | N/A |
| `macro_data_refresh` | All | 4 hours | N/A |
| `news_fetch` | All | 30 min | N/A |

### Data Storage

- **Format**: Apache Parquet (snappy compression)
- **Location**: `data/processed/{exchange}_{SYMBOL}_{timeframe}.parquet`
- **Locking**: File-level locks prevent concurrent write corruption
- **Deduplication**: Automatic on load (keep last)

---

## Framework Containers

### Port Allocation

**Dev group (aitp-dev)** — `docker-compose.yml`

| Service | Port | Profile |
|---------|------|---------|
| Django Backend | 4000 | default |
| React Frontend | 4001 | default |
| Freqtrade CIV1 | 4080 | trading |
| Freqtrade BMR | 4083 | trading |
| Freqtrade VB | 4084 | trading |
| NautilusTrader Worker | 4090 | research |
| VectorBT Worker | 4092 | research |
| Redis | 4013 | trading/research |
| Prometheus | 4010 | monitoring |
| Grafana | 4011 | monitoring |

**Prod group (aitp-prod)** — `docker-compose.prod.yml`

| Service | Port | Profile |
|---------|------|---------|
| Django Backend | 4100 | default |
| React Frontend | 4101 | default |
| Freqtrade CIV1 | 4180 | trading |
| Freqtrade BMR | 4183 | trading |
| Freqtrade VB | 4184 | trading |
| NautilusTrader Worker | 4190 | research |
| VectorBT Worker | 4192 | research |
| Redis | 4113 | trading/research |
| Prometheus | 4110 | monitoring |
| Grafana | 4111 | monitoring |

Dev and prod groups are fully isolated — separate Docker networks, volumes, and container names. No cross-references.

### Start All Frameworks

```bash
# Start everything (backend + frontend + trading + research)
doppler run -- make docker-up
doppler run -- make frameworks-up

# Or individually
doppler run -- make trading-up      # Freqtrade containers only
doppler run -- make research-up     # NautilusTrader + VectorBT + Redis

# Check status
make frameworks-status

# Stop frameworks
make frameworks-down
```

### Freqtrade Containers

Three core strategies run as separate containers:

| Container | Strategy | Port | Dry Wallet |
|-----------|----------|------|-----------|
| `aitp-dev-ft-civ1` | CryptoInvestorV1 | 4080 | 500 USDT |
| `aitp-dev-ft-bmr` | BollingerMeanReversion | 4083 | 500 USDT |
| `aitp-dev-ft-vb` | VolatilityBreakout | 4084 | 300 USDT |

All run in **dry-run mode** by default. Exchange keys are injected via Doppler.

### NautilusTrader Worker

Multi-asset backtesting engine running 7 strategies across crypto, equity, and forex.

```bash
# Health check
curl http://localhost:4090/health

# List strategies
curl http://localhost:4090/strategies

# Run a backtest
curl -X POST http://localhost:4090/backtest \
  -H "Content-Type: application/json" \
  -d '{"strategy": "NautilusTrendFollowing", "symbol": "BTC/USDT", "timeframe": "1h"}'

# Batch backtest (all crypto strategies)
curl -X POST http://localhost:4090/backtest/batch \
  -H "Content-Type: application/json" \
  -d '{"asset_class": "crypto"}'
```

### VectorBT Worker

High-speed parameter screening engine with 5 strategy types and 300+ parameter combinations.

```bash
# Health check
curl http://localhost:4092/health

# List screening strategies
curl http://localhost:4092/strategies

# Screen a single symbol
curl -X POST http://localhost:4092/screen \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC/USDT", "timeframe": "1h"}'

# Batch screen (all crypto watchlist)
curl -X POST http://localhost:4092/screen/batch \
  -H "Content-Type: application/json" \
  -d '{"asset_class": "crypto"}'
```

---

## Security Best Practices

### API Key Management

- **Never enable withdrawal permissions** unless absolutely necessary
- **Restrict API keys to your IP address** when the exchange supports it
- **Use separate API keys** for this platform — do not reuse keys from other apps
- **Never share API keys** or commit them to version control
- **Rotate keys regularly** (every 90 days recommended)
- **Start with read-only permissions** until you are ready for live trading

### Credential Encryption

All exchange credentials stored via the web UI are encrypted at rest using **Fernet symmetric encryption** (AES-128-CBC with HMAC-SHA256). The encryption key is managed via the `DJANGO_ENCRYPTION_KEY` Doppler secret. The API never returns raw credentials — only masked versions (e.g., `abcd****mnop`).

### Sandbox / Testnet Environments

All exchanges offer testnet environments for paper trading. **Always start in sandbox mode** before using real funds.

| Exchange | Testnet URL | Notes |
|----------|-------------|-------|
| Binance | https://testnet.binance.vision | Separate signup, free test funds |
| Bybit | https://testnet.bybit.com | Separate signup, free test funds |
| Kraken | https://demo-futures.kraken.com | Futures testnet only |
| KuCoin | https://sandbox.kucoin.com | Separate signup |

To use sandbox mode:
- **Web UI**: Check the "Sandbox mode" checkbox when adding an exchange
- **Platform config**: Set `sandbox: true` in `configs/platform_config.yaml`
- **Freqtrade**: Set `"dry_run": true` in `freqtrade/config.json.example`

The platform config enforces a minimum of 14 days paper trading before live (`min_paper_trade_days: 14`).

### Security Summary

| Layer | Protection |
|-------|------------|
| Transport | HTTPS (TLS certs via `make certs`) |
| Authentication | Django session-based auth, CSRF protection |
| API credentials | Fernet encryption at rest (AES-128-CBC) |
| API responses | Credentials masked, never returned in plaintext |
| Secrets management | Doppler (never stored in `.env` or code) |
| Database backups | GPG-encrypted via `BACKUP_ENCRYPTION_KEY` |
| Password hashing | Argon2id (Django default) |
| Sandbox enforcement | 14-day paper trading minimum before live |

---

## Verification & Troubleshooting

### Quick Health Check

```bash
# Platform preflight (checks all subsystems)
doppler run -- docker compose exec backend python manage.py pilot_preflight

# Platform status
doppler run -- docker compose exec backend python manage.py pilot_status

# Framework container health
make frameworks-status
```

### Exchange Authentication Verification

```bash
# Test Kraken connectivity
doppler run -- docker compose exec backend python -c "
from market.services.exchange import ExchangeService
import asyncio

async def test():
    svc = ExchangeService('kraken')
    ticker = await svc.fetch_ticker('BTC/USDT')
    print(f'BTC/USDT: \${ticker[\"last\"]:,.2f}')
    await svc.close()

asyncio.run(test())
"

# Test yfinance (no auth needed)
doppler run -- docker compose exec backend python -c "
from market.services.yfinance_service import YFinanceService
import asyncio

async def test():
    svc = YFinanceService()
    ticker = await svc.fetch_ticker('AAPL/USD', 'equity')
    print(f'AAPL: \${ticker[\"last\"]:,.2f}')

asyncio.run(test())
"
```

### Exchange Connection Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `AuthenticationError` | Invalid API key or secret | Re-check credentials, regenerate if needed |
| `ExchangeNotAvailable` | Exchange is down or blocked | Try again later, check exchange status page |
| `NetworkError` | No internet or firewall blocking | Check network, ensure exchange API is reachable |
| `InvalidNonce` | Clock sync issue | Sync system clock (`timedatectl set-ntp true`) |
| `PermissionDenied` | Insufficient API permissions | Enable required permissions in exchange API settings |
| `Sandbox not supported` | Exchange has no testnet for that mode | Uncheck sandbox mode or use a different exchange |

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `DJANGO_SECRET_KEY not set` | Missing Doppler setup | `make doppler-setup` |
| `FREQTRADE_USERNAME not set` | Missing env var | `doppler secrets set FREQTRADE_USERNAME=freqtrader` |
| Exchange returns empty data | API key not configured | Set `KRAKEN_API_KEY` in Doppler |
| KuCoin "Passphrase required" | KuCoin API keys require a passphrase | Enter passphrase set during key creation in `KUCOIN_PASSPHRASE` |
| yfinance returns no data | Market closed / symbol wrong | Check symbol format (AAPL not AAPL/USD for direct calls) |
| FRED returns 403 | Missing or expired API key | Get new key from FRED website |
| Rate limiting errors | Too many API requests | Reduce number of symbols or increase fetch interval |
| IP restriction errors | API key restricted to different IP | Whitelist the IP of the machine running A1SI-AITP |
| VectorBT worker 503 | Package install failed | Check `docker compose logs vectorbt` |
| NautilusTrader fallback mode | Native engine not compiled | Expected on some platforms; pandas mode is functional |

### Logs

```bash
# Backend logs
make docker-logs-backend

# Freqtrade logs
docker compose --profile trading logs -f freqtrade-civ1

# NautilusTrader worker logs
docker compose --profile research logs -f nautilus

# VectorBT worker logs
docker compose --profile research logs -f vectorbt
```

---

## Complete Setup Checklist

1. [ ] Install Doppler CLI: `brew install dopplerhq/cli/doppler`
2. [ ] Authenticate: `doppler login`
3. [ ] Link project: `make doppler-setup`
4. [ ] Set Kraken API keys in Doppler
5. [ ] Set FRED API key in Doppler (optional)
6. [ ] Set NewsAPI key in Doppler (optional)
7. [ ] Set Telegram bot token for alerts (optional)
8. [ ] Build Docker images: `make docker-build`
9. [ ] Start backend + frontend: `doppler run -- make docker-up`
10. [ ] Start framework containers: `doppler run -- make frameworks-up`
11. [ ] Download initial data: `doppler run -- docker compose exec backend python run.py data download`
12. [ ] Verify: `doppler run -- docker compose exec backend python manage.py pilot_preflight`
