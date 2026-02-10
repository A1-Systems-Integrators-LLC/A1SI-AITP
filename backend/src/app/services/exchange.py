import ccxt.async_support as ccxt

from app.config import settings
from app.schemas.exchange import ExchangeInfo
from app.schemas.market import OHLCVData, TickerData

# Exchanges we support in the UI
SUPPORTED_EXCHANGES = ["binance", "coinbase", "kraken", "kucoin", "bybit"]


class ExchangeService:
    def __init__(self, exchange_id: str | None = None) -> None:
        self._exchange_id = exchange_id or settings.exchange_id
        self._exchange: ccxt.Exchange | None = None

    async def _get_exchange(self) -> ccxt.Exchange:
        if self._exchange is None:
            exchange_class = getattr(ccxt, self._exchange_id)
            config: dict[str, object] = {"enableRateLimit": True}
            if settings.exchange_api_key:
                config["apiKey"] = settings.exchange_api_key
                config["secret"] = settings.exchange_api_secret
            self._exchange = exchange_class(config)
        return self._exchange

    async def close(self) -> None:
        if self._exchange is not None:
            await self._exchange.close()
            self._exchange = None

    def list_exchanges(self) -> list[ExchangeInfo]:
        result = []
        for eid in SUPPORTED_EXCHANGES:
            exchange_class = getattr(ccxt, eid)
            ex = exchange_class()
            result.append(
                ExchangeInfo(
                    id=eid,
                    name=ex.name,
                    countries=getattr(ex, "countries", []) or [],
                    has_fetch_tickers=ex.has.get("fetchTickers", False),
                    has_fetch_ohlcv=ex.has.get("fetchOHLCV", False),
                )
            )
        return result

    async def fetch_ticker(self, symbol: str) -> TickerData:
        exchange = await self._get_exchange()
        ticker = await exchange.fetch_ticker(symbol)
        from datetime import datetime, timezone

        return TickerData(
            symbol=ticker["symbol"],
            price=ticker["last"] or 0.0,
            volume_24h=ticker.get("quoteVolume") or 0.0,
            change_24h=ticker.get("percentage") or 0.0,
            high_24h=ticker.get("high") or 0.0,
            low_24h=ticker.get("low") or 0.0,
            timestamp=datetime.fromtimestamp(
                (ticker["timestamp"] or 0) / 1000, tz=timezone.utc
            ),
        )

    async def fetch_tickers(self, symbols: list[str] | None = None) -> list[TickerData]:
        exchange = await self._get_exchange()
        tickers = await exchange.fetch_tickers(symbols)
        from datetime import datetime, timezone

        result = []
        for ticker in tickers.values():
            result.append(
                TickerData(
                    symbol=ticker["symbol"],
                    price=ticker["last"] or 0.0,
                    volume_24h=ticker.get("quoteVolume") or 0.0,
                    change_24h=ticker.get("percentage") or 0.0,
                    high_24h=ticker.get("high") or 0.0,
                    low_24h=ticker.get("low") or 0.0,
                    timestamp=datetime.fromtimestamp(
                        (ticker["timestamp"] or 0) / 1000, tz=timezone.utc
                    ),
                )
            )
        return result

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> list[OHLCVData]:
        exchange = await self._get_exchange()
        data = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return [
            OHLCVData(
                timestamp=candle[0],
                open=candle[1],
                high=candle[2],
                low=candle[3],
                close=candle[4],
                volume=candle[5],
            )
            for candle in data
        ]

    async def fetch_markets(self) -> list[dict]:
        exchange = await self._get_exchange()
        return await exchange.load_markets()
