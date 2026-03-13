# IEB Phase 9: Asset-Class Specific Tuning

## Status: COMPLETE

## Summary

Added per-asset-class parameter overrides so the conviction system adapts to each market's characteristics (volatility, session hours, spread profiles, volume reliability).

## Changes

| File | Action | Details |
|------|--------|---------|
| `common/signals/asset_tuning.py` | NEW | `AssetClassConfig` dataclass, `ASSET_CONFIGS`, `get_config()`, `get_conviction_threshold()`, `get_session_adjustment()` |
| `common/signals/aggregator.py` | MODIFIED | Uses per-class conviction threshold, cooldown bars, volume weight bonus; `ENTRY_TIER_OFFSETS` (relative); `CompositeSignal` has `conviction_threshold` + `session_adjustment` fields |
| `common/signals/exit_manager.py` | MODIFIED | `_check_time_exit()` applies `max_hold_multiplier` before regime multiplier |
| `common/signals/constants.py` | MODIFIED | Removed `REJECT_THRESHOLD`, `REGIME_COOLDOWN_BARS`; renamed `ENTRY_TIERS` → `ENTRY_TIER_OFFSETS` (relative offsets) |
| `common/signals/__init__.py` | MODIFIED | Exports `AssetClassConfig`, `get_config`, `get_session_adjustment` |
| `backend/tests/test_asset_tuning.py` | NEW | ~35 tests covering all configs, session adjustments, aggregator integration, exit manager integration |
| `backend/tests/test_signal_aggregation.py` | MODIFIED | Updated imports for renamed/removed constants |

## Per-Asset-Class Configs

| Parameter | Crypto | Equity | Forex |
|-----------|--------|--------|-------|
| conviction_threshold | 55 | 65 | 60 |
| regime_cooldown_bars | 6 | 3 | 4 |
| max_hold_multiplier | 1.0 | 2.0 | 0.7 |
| volume_weight_bonus | 1.0 | 1.3 | 0.5 |
| spread_max_pct | 0.5% | 0.2% | 0.1% |
| session_bonus | none | none | London-NY: -10, Asian: +5, Dead zone: +15 |

## Design Decisions

1. **Threshold tiers are relative**: `ENTRY_TIER_OFFSETS` are offsets from conviction_threshold (strong_buy = +20, buy = +10, cautious_buy = +0)
2. **Backward compatible**: Crypto config matches all previous global defaults
3. **Session adjustment is additive**: Applied to the threshold, not the score
4. **Volume bonus is multiplicative**: scanner_score * volume_weight_bonus before weighting
5. **Spread gating is future-ready**: `spread_max_pct` stored but not enforced yet
