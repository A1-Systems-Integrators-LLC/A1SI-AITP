"""Risk manager validation with real price data."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.data_pipeline.pipeline import load_ohlcv  # noqa: E402
from common.regime.regime_detector import RegimeDetector  # noqa: E402
from common.regime.strategy_router import StrategyRouter  # noqa: E402
from common.risk.risk_manager import RiskManager  # noqa: E402

rm = RiskManager()
detector = RegimeDetector()
router = StrategyRouter()

print("=== RISK MANAGER VALIDATION (Real Kraken Data) ===\n")

# Feed real price data to return tracker
for symbol in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
    df = load_ohlcv(symbol, "1d", "kraken")
    if df.empty:
        continue
    for price in df["close"].values:
        rm.return_tracker.record_price(symbol, float(price))
    n_ret = len(rm.return_tracker.get_returns(symbol))
    print(f"{symbol}: fed {len(df)} daily prices, {n_ret} returns")

print("\n--- Position Sizing Tests ---")
state = detector.detect(load_ohlcv("BTC/USDT", "1d", "kraken"))
decision = router.route(state)
btc_price = float(load_ohlcv("BTC/USDT", "1d", "kraken")["close"].iloc[-1])
stop_loss = btc_price * 0.97

size = rm.calculate_position_size(
    entry_price=btc_price,
    stop_loss_price=stop_loss,
    regime_modifier=decision.position_size_modifier,
)
print(f"BTC entry={btc_price:.0f}, stop={stop_loss:.0f}, regime={decision.regime.value}")
val = size * btc_price
print(f"Position size: {size:.6f} BTC (value: {val:.2f})")

print("\n--- Trade Check Tests ---")
approved, reason = rm.check_new_trade("BTC/USDT", "buy", size, btc_price, stop_loss)
label = "APPROVED" if approved else "REJECTED"
print(f"BTC trade: {label} ({reason})")

rm.register_trade("BTC/USDT", "buy", size, btc_price)
eth_price = float(load_ohlcv("ETH/USDT", "1d", "kraken")["close"].iloc[-1])
eth_stop = eth_price * 0.97
eth_size = rm.calculate_position_size(eth_price, eth_stop, regime_modifier=0.5)
approved2, reason2 = rm.check_new_trade("ETH/USDT", "buy", eth_size, eth_price, eth_stop)
label2 = "APPROVED" if approved2 else "REJECTED"
print(f"ETH trade: {label2} ({reason2})")

print("\n--- Correlation Matrix ---")
corr = rm.return_tracker.get_correlation_matrix()
if not corr.empty:
    print(corr.round(3).to_string())

print("\n--- Portfolio VaR (Parametric) ---")
rm.register_trade("ETH/USDT", "buy", eth_size, eth_price)
var_result = rm.get_var("parametric")
print(f"95% VaR: {var_result.var_95:.2f}")
print(f"99% VaR: {var_result.var_99:.2f}")
print(f"95% CVaR: {var_result.cvar_95:.2f}")
print(f"99% CVaR: {var_result.cvar_99:.2f}")
print(f"Window: {var_result.window_days} days")

var_hist = rm.get_var("historical")
print("\n--- Portfolio VaR (Historical) ---")
print(f"95% VaR: {var_hist.var_95:.2f}")
print(f"99% VaR: {var_hist.var_99:.2f}")

print("\n--- Portfolio Heat Check ---")
heat = rm.portfolio_heat_check()
print(json.dumps(heat, indent=2, default=str))

print("\n--- Drawdown Halt Test ---")
rm.update_equity(8400)  # 16% drawdown from 10000
print(f"Halted: {rm.state.is_halted}, Reason: {rm.state.halt_reason}")
