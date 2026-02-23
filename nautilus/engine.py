"""
NautilusTrader Engine Adapter
==============================
Configures a real BacktestEngine with proper Venue, Instrument, and
Bar data when nautilus_trader is installed. Falls back gracefully
when the library is not available.

Usage:
    from nautilus.engine import HAS_NAUTILUS_TRADER, create_backtest_engine
    if HAS_NAUTILUS_TRADER:
        engine, instrument = create_backtest_engine(...)
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
    from nautilus_trader.config import LoggingConfig
    from nautilus_trader.model.currencies import USDT
    from nautilus_trader.model.data import Bar, BarSpecification, BarType
    from nautilus_trader.model.enums import (
        AccountType,
        AggregationSource,
        BarAggregation,
        OmsType,
        PriceType,
    )
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.instruments import CurrencyPair
    from nautilus_trader.model.objects import Currency, Money, Price, Quantity

    HAS_NAUTILUS_TRADER = True
except ImportError:
    HAS_NAUTILUS_TRADER = False


CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "platform_config.yaml"


def _load_nautilus_config() -> dict:
    """Load nautilus section from platform_config.yaml."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        import yaml

        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("nautilus", {})
    except (ImportError, Exception):
        return {}


# ── Timeframe Mapping ───────────────────────────────


_BAR_AGG_MAP: dict[str, tuple[int, str]] = {
    "1m": (1, "MINUTE"),
    "5m": (5, "MINUTE"),
    "15m": (15, "MINUTE"),
    "1h": (1, "HOUR"),
    "4h": (4, "HOUR"),
    "1d": (1, "DAY"),
}


def _parse_bar_spec(timeframe: str) -> tuple[int, str]:
    """Convert '1h' to (1, 'HOUR') for BarType construction."""
    return _BAR_AGG_MAP.get(timeframe, (1, "HOUR"))


# ── Engine Factory ──────────────────────────────────


def create_backtest_engine(
    trader_id: str = "CRYPTO_INVESTOR-001",
    log_level: str = "WARNING",
) -> "BacktestEngine":
    """Create and configure a NautilusTrader BacktestEngine.

    Returns the engine instance. Raises ImportError if nautilus_trader
    is not installed.
    """
    if not HAS_NAUTILUS_TRADER:
        raise ImportError("nautilus_trader is not installed")

    config = BacktestEngineConfig(
        logging=LoggingConfig(log_level=log_level),
        trader_id=trader_id,
    )
    engine = BacktestEngine(config=config)
    logger.info(f"BacktestEngine created: trader_id={trader_id}")
    return engine


def add_venue(
    engine: "BacktestEngine",
    venue_name: str = "BINANCE",
    oms_type: str = "NETTING",
    account_type: str = "CASH",
    starting_balance: float = 10000.0,
) -> "Venue":
    """Add a simulated venue to the engine."""
    if not HAS_NAUTILUS_TRADER:
        raise ImportError("nautilus_trader is not installed")

    venue = Venue(venue_name)
    oms = OmsType[oms_type]
    acct = AccountType[account_type]

    engine.add_venue(
        venue=venue,
        oms_type=oms,
        account_type=acct,
        base_currency=None,  # multi-currency for CurrencyPair instruments
        starting_balances=[Money(starting_balance, USDT)],
    )
    logger.info(f"Venue added: {venue_name}, balance={starting_balance} USDT")
    return venue


def create_crypto_instrument(
    symbol: str = "BTC/USDT",
    venue_name: str = "BINANCE",
) -> "CurrencyPair":
    """Create a crypto spot CurrencyPair for backtesting.

    Returns a CurrencyPair instrument that can be added to the engine
    via ``engine.add_instrument()``.
    """
    if not HAS_NAUTILUS_TRADER:
        raise ImportError("nautilus_trader is not installed")

    from decimal import Decimal

    parts = symbol.split("/")
    base_str = parts[0] if len(parts) == 2 else symbol.replace("USDT", "")
    quote_str = parts[1] if len(parts) == 2 else "USDT"
    safe_symbol = symbol.replace("/", "")

    instrument_id = InstrumentId(
        symbol=Symbol(safe_symbol),
        venue=Venue(venue_name),
    )
    return CurrencyPair(
        instrument_id=instrument_id,
        raw_symbol=Symbol(safe_symbol),
        base_currency=Currency.from_str(base_str),
        quote_currency=Currency.from_str(quote_str),
        price_precision=2,
        size_precision=6,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_str("0.000001"),
        maker_fee=Decimal("0.001"),
        taker_fee=Decimal("0.001"),
        ts_event=0,
        ts_init=0,
    )


def build_bar_type(
    instrument_id: "InstrumentId",
    timeframe: str = "1h",
) -> "BarType":
    """Construct a BarType for the given instrument and timeframe."""
    if not HAS_NAUTILUS_TRADER:
        raise ImportError("nautilus_trader is not installed")

    step, agg_name = _parse_bar_spec(timeframe)

    bar_spec = BarSpecification(
        step=step,
        aggregation=BarAggregation[agg_name],
        price_type=PriceType.LAST,
    )
    return BarType(
        instrument_id=instrument_id,
        bar_spec=bar_spec,
        aggregation_source=AggregationSource.EXTERNAL,
    )


def convert_df_to_bars(
    df: pd.DataFrame,
    bar_type: "BarType",
    price_precision: int = 2,
    size_precision: int = 6,
) -> list["Bar"]:
    """Convert a pandas OHLCV DataFrame to a list of NautilusTrader Bar objects."""
    if not HAS_NAUTILUS_TRADER:
        raise ImportError("nautilus_trader is not installed")

    pfmt = f".{price_precision}f"
    sfmt = f".{size_precision}f"
    bars = []
    for ts, row in df.iterrows():
        ts_ns = int(ts.value)  # nanoseconds since epoch
        bar = Bar(
            bar_type=bar_type,
            open=Price.from_str(f"{row['open']:{pfmt}}"),
            high=Price.from_str(f"{row['high']:{pfmt}}"),
            low=Price.from_str(f"{row['low']:{pfmt}}"),
            close=Price.from_str(f"{row['close']:{pfmt}}"),
            volume=Quantity.from_str(f"{row['volume']:{sfmt}}"),
            ts_event=ts_ns,
            ts_init=ts_ns,
        )
        bars.append(bar)

    logger.info(f"Converted {len(bars)} bars for {bar_type}")
    return bars
