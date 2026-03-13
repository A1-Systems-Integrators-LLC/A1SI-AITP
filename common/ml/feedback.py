"""ML Feedback Tracker
===================
Tracks prediction outcomes, computes model accuracy, and triggers retraining.
Storage: JSONL files in models/_feedback/ to avoid SQLite write contention.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.ml.registry import DEFAULT_MODELS_DIR

logger = logging.getLogger(__name__)


class FeedbackTracker:
    """Tracks ML prediction outcomes and determines retraining needs.

    Records are stored as JSONL (one JSON object per line) in:
        models/_feedback/YYYY-MM-DD.jsonl

    Each record contains: model_id, symbol, asset_class, probability,
    direction, regime, actual_direction (filled later), correct (filled later).
    """

    def __init__(self, feedback_dir: Path | None = None):
        self._feedback_dir = feedback_dir or (DEFAULT_MODELS_DIR / "_feedback")
        self._feedback_dir.mkdir(parents=True, exist_ok=True)

    def record_prediction(
        self,
        model_id: str,
        symbol: str,
        asset_class: str,
        probability: float,
        direction: str,
        regime: str = "",
        timestamp: str | None = None,
    ) -> dict:
        """Record a prediction for later outcome matching.

        Args:
            model_id: ID of the model that made the prediction.
            symbol: Trading symbol.
            asset_class: Asset class.
            probability: Predicted probability.
            direction: Predicted direction ("up"/"down").
            regime: Current market regime.
            timestamp: Optional ISO timestamp (defaults to now).

        Returns:
            The recorded prediction dict.

        """
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        record = {
            "model_id": model_id,
            "symbol": symbol,
            "asset_class": asset_class,
            "probability": round(probability, 4),
            "direction": direction,
            "regime": regime,
            "timestamp": ts,
            "actual_direction": None,
            "correct": None,
        }

        date_str = ts[:10]  # YYYY-MM-DD
        filepath = self._feedback_dir / f"{date_str}.jsonl"
        with open(filepath, "a") as f:
            f.write(json.dumps(record) + "\n")

        return record

    def backfill_outcomes(
        self,
        actual_returns: dict[str, float],
        date: str | None = None,
    ) -> int:
        """Match unresolved predictions with actual returns.

        Args:
            actual_returns: Dict mapping symbol → actual return (positive = up).
            date: Date to process (YYYY-MM-DD). Defaults to today.

        Returns:
            Number of records updated.

        """
        date_str = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = self._feedback_dir / f"{date_str}.jsonl"
        if not filepath.exists():
            return 0

        records = self._load_records(filepath)
        updated_count = 0

        for record in records:
            if record.get("actual_direction") is not None:
                continue

            symbol = record.get("symbol", "")
            if symbol not in actual_returns:
                continue

            actual_return = actual_returns[symbol]
            actual_dir = "up" if actual_return > 0 else "down"
            record["actual_direction"] = actual_dir
            record["correct"] = record["direction"] == actual_dir
            record["actual_return"] = round(actual_return, 6)
            updated_count += 1

        if updated_count > 0:
            self._save_records(filepath, records)

        logger.info("Backfilled %d outcomes for %s", updated_count, date_str)
        return updated_count

    def get_model_accuracy(
        self,
        model_id: str,
        lookback_days: int = 30,
    ) -> dict[str, Any]:
        """Compute accuracy metrics for a specific model.

        Args:
            model_id: Model identifier.
            lookback_days: Number of days to look back.

        Returns:
            Dict with accuracy, total_predictions, correct_predictions,
            accuracy_by_regime, accuracy_by_asset_class.

        """
        records = self._load_recent_records(lookback_days)

        model_records = [
            r for r in records if r.get("model_id") == model_id and r.get("correct") is not None
        ]

        if not model_records:
            return {
                "model_id": model_id,
                "total_predictions": 0,
                "correct_predictions": 0,
                "accuracy": 0.0,
                "accuracy_by_regime": {},
                "accuracy_by_asset_class": {},
            }

        total = len(model_records)
        correct = sum(1 for r in model_records if r["correct"])

        # Accuracy by regime
        by_regime: dict[str, list[bool]] = {}
        for r in model_records:
            regime = r.get("regime", "unknown")
            by_regime.setdefault(regime, []).append(r["correct"])

        accuracy_by_regime = {
            k: round(sum(v) / len(v), 4) if v else 0.0 for k, v in by_regime.items()
        }

        # Accuracy by asset class
        by_ac: dict[str, list[bool]] = {}
        for r in model_records:
            ac = r.get("asset_class", "unknown")
            by_ac.setdefault(ac, []).append(r["correct"])

        accuracy_by_ac = {k: round(sum(v) / len(v), 4) if v else 0.0 for k, v in by_ac.items()}

        return {
            "model_id": model_id,
            "total_predictions": total,
            "correct_predictions": correct,
            "accuracy": round(correct / total, 4),
            "accuracy_by_regime": accuracy_by_regime,
            "accuracy_by_asset_class": accuracy_by_ac,
        }

    def should_retrain(
        self,
        model_id: str,
        accuracy_threshold: float = 0.52,
        min_predictions: int = 50,
        stale_days: int = 7,
    ) -> bool:
        """Determine if a model should be retrained.

        Reasons:
        1. Accuracy dropped below threshold (with enough samples)
        2. Model is stale (no predictions in stale_days)
        3. Regime has shifted (accuracy varies >15% across regimes)

        Args:
            model_id: Model identifier.
            accuracy_threshold: Minimum acceptable accuracy.
            min_predictions: Minimum predictions before judging accuracy.
            stale_days: Days without predictions to trigger retrain.

        Returns:
            True if retraining is recommended.

        """
        stats = self.get_model_accuracy(model_id, lookback_days=30)

        # No predictions at all → stale
        if stats["total_predictions"] == 0:
            return True

        # Check staleness: look at last few days only
        recent = self._load_recent_records(stale_days)
        recent_for_model = [r for r in recent if r.get("model_id") == model_id]
        if not recent_for_model:
            return True

        # Accuracy check (only with enough samples)
        if (
            stats["total_predictions"] >= min_predictions
            and stats["accuracy"] < accuracy_threshold
        ):
                logger.info(
                    "Model %s below accuracy threshold: %.4f < %.4f",
                    model_id,
                    stats["accuracy"],
                    accuracy_threshold,
                )
                return True

        # Regime shift: high variance across regimes
        regime_accs = list(stats["accuracy_by_regime"].values())
        if len(regime_accs) >= 2:
            regime_spread = max(regime_accs) - min(regime_accs)
            if regime_spread > 0.15:
                logger.info(
                    "Model %s has high regime variance: %.4f spread",
                    model_id,
                    regime_spread,
                )
                return True

        return False

    def get_all_model_stats(self, lookback_days: int = 30) -> list[dict]:
        """Get accuracy stats for all models with feedback data.

        Returns:
            List of accuracy dicts, one per model.

        """
        records = self._load_recent_records(lookback_days)
        model_ids = set(r.get("model_id", "") for r in records if r.get("model_id"))

        return [self.get_model_accuracy(mid, lookback_days) for mid in sorted(model_ids)]

    def _load_records(self, filepath: Path) -> list[dict]:
        """Load all records from a JSONL file."""
        records = []
        if not filepath.exists():
            return records
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping corrupt record in %s", filepath)
        return records

    def _save_records(self, filepath: Path, records: list[dict]) -> None:
        """Rewrite a JSONL file with updated records."""
        with open(filepath, "w") as f:
            f.writelines(json.dumps(record) + "\n" for record in records)

    def _load_recent_records(self, lookback_days: int) -> list[dict]:
        """Load records from the last N days."""
        from datetime import timedelta

        all_records: list[dict] = []
        today = datetime.now(timezone.utc).date()

        for i in range(lookback_days):
            date = today - timedelta(days=i)
            filepath = self._feedback_dir / f"{date.isoformat()}.jsonl"
            all_records.extend(self._load_records(filepath))

        return all_records
