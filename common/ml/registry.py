"""ML Model Registry
=================
Filesystem-based model storage with versioning and metadata tracking.
Models stored in: models/<model_id>/{model.txt, manifest.json}
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import lightgbm as lgb

    HAS_LIGHTGBM = True
except ImportError:  # pragma: no cover
    HAS_LIGHTGBM = False
    lgb = None  # type: ignore[assignment]

try:
    from common.ml.lstm_model import LSTMPredictor

    HAS_LSTM = True
except ImportError:  # pragma: no cover
    HAS_LSTM = False
    LSTMPredictor = None  # type: ignore[assignment, misc]

# Default models directory — relative to project root
DEFAULT_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"


class ModelRegistry:
    """Filesystem-based model registry.

    Directory layout:
        models/
            <model_id>/
                model.txt       — LightGBM model file
                manifest.json   — metadata, metrics, feature list
    """

    def __init__(self, models_dir: Path | None = None):
        self.models_dir = models_dir or DEFAULT_MODELS_DIR
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def save_model(
        self,
        model: object,
        metrics: dict,
        metadata: dict,
        feature_importance: dict,
        symbol: str = "",
        timeframe: str = "",
        label: str = "",
    ) -> str:
        """Save a trained model and its metadata.

        Args:
            model: Trained model (LGBMClassifier, XGBClassifier, or LSTMPredictor).
            metrics: Training metrics dict.
            metadata: Training metadata dict.
            feature_importance: Feature importance scores.
            symbol: Trading symbol used for training.
            timeframe: Timeframe of training data.
            label: Optional human label.

        Returns:
            model_id string.

        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_id = f"{ts}_{symbol.replace('/', '')}_{timeframe}" if symbol else ts

        model_dir = self.models_dir / model_id
        model_dir.mkdir(parents=True, exist_ok=True)

        # Save model — detect type
        model_path = model_dir / "model.txt"
        model_format = "lightgbm"

        # LSTM (torch) model
        if HAS_LSTM and isinstance(model, LSTMPredictor):
            model_path = model_dir / "model.pt"
            model.save(model_path)
            model_format = "lstm"
        else:
            if not HAS_LIGHTGBM:
                raise ImportError("lightgbm required to save tree models")
            # Check if XGBoost model
            try:
                import xgboost as _xgb

                if isinstance(model, _xgb.XGBClassifier):
                    model_path = model_dir / "model.json"
                    xgb_booster = model.get_booster()
                    xgb_booster.save_model(str(model_path))
                    model_format = "xgboost"
                else:
                    booster = getattr(model, "booster_", model)
                    booster.save_model(str(model_path))
            except ImportError:
                booster = getattr(model, "booster_", model)
                booster.save_model(str(model_path))

        # Save manifest
        manifest = {
            "model_id": model_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "timeframe": timeframe,
            "label": label,
            "model_format": model_format,
            "metrics": metrics,
            "metadata": metadata,
            "feature_importance": feature_importance,
        }
        manifest_path = model_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str))

        logger.info("Model saved: %s (accuracy=%.4f)", model_id, metrics.get("accuracy", 0))
        return model_id

    def load_model(self, model_id: str) -> tuple[object, dict]:
        """Load a model and its manifest.

        Args:
            model_id: The model identifier.

        Returns:
            Tuple of (model, manifest dict). Model type depends on format:
            - lightgbm: LGBMClassifier
            - xgboost: XGBClassifier
            - lstm: LSTMPredictor

        Raises:
            FileNotFoundError: If model_id doesn't exist.
            ImportError: If required library not installed.

        """
        model_dir = self.models_dir / model_id
        if not model_dir.exists():
            raise FileNotFoundError(f"Model not found: {model_id}")

        manifest_path = model_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())

        model_format = manifest.get("model_format", "lightgbm")

        # LSTM (torch) model
        if model_format == "lstm":
            if not HAS_LSTM:
                raise ImportError("torch required to load LSTM models")
            model_path = model_dir / "model.pt"
            return LSTMPredictor.load(model_path), manifest

        if model_format == "xgboost":
            try:
                import xgboost as _xgb

                model_path = model_dir / "model.json"
                clf = _xgb.XGBClassifier()
                clf.load_model(str(model_path))
                return clf, manifest
            except ImportError as err:
                raise ImportError("xgboost required to load this model") from err

        # LightGBM load
        if not HAS_LIGHTGBM:
            raise ImportError("lightgbm required to load models")

        model_path = model_dir / "model.txt"
        booster = lgb.Booster(model_file=str(model_path))

        # Wrap raw Booster in LGBMClassifier so callers can use
        # predict_proba(). LightGBM 4.x save_model() strips the sklearn
        # wrapper, so we reconstruct it here.
        import numpy as np

        clf = lgb.LGBMClassifier()
        clf._Booster = booster
        clf.fitted_ = True
        clf._n_features = booster.num_feature()
        clf._n_classes = 2  # binary classifier
        classes = np.array([0, 1])
        clf._le = type(
            "LabelEncoder", (), {
                "classes_": classes,
                "inverse_transform": lambda self, y: classes[y],
            },
        )()

        return clf, manifest

    def list_models(self) -> list[dict]:
        """List all models with summary metadata.

        Returns:
            List of manifest dicts (sorted newest first).

        """
        models = []
        if not self.models_dir.exists():
            return models

        for model_dir in sorted(self.models_dir.iterdir(), reverse=True):
            if not model_dir.is_dir():
                continue
            manifest_path = model_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text())
                models.append(
                    {
                        "model_id": manifest.get("model_id", model_dir.name),
                        "created_at": manifest.get("created_at", ""),
                        "symbol": manifest.get("symbol", ""),
                        "timeframe": manifest.get("timeframe", ""),
                        "label": manifest.get("label", ""),
                        "metrics": manifest.get("metrics", {}),
                    }
                )
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Skipping corrupt manifest in %s: %s", model_dir, e)

        return models

    def get_model_detail(self, model_id: str) -> dict | None:
        """Get full manifest for a specific model.

        Returns:
            Full manifest dict or None if not found.

        """
        model_dir = self.models_dir / model_id
        manifest_path = model_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            return json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, KeyError):
            return None

    def delete_model(self, model_id: str) -> bool:
        """Delete a model and its directory.

        Returns:
            True if deleted, False if not found.

        """
        import shutil

        model_dir = self.models_dir / model_id
        if not model_dir.exists():
            return False
        shutil.rmtree(model_dir)
        logger.info("Model deleted: %s", model_id)
        return True
