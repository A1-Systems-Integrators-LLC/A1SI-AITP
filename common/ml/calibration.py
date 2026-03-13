"""
ML Prediction Calibration
=========================
Platt scaling for probability calibration plus rolling accuracy tracking.
Calibration parameters stored as calibration.json alongside model files.
"""

import json
import logging
import math
import threading
from collections import deque
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class PredictionCalibrator:
    """Platt scaling calibrator with rolling accuracy tracking.

    Calibrated probability: 1 / (1 + exp(a * raw + b))
    where a and b are fitted on the test set after training.

    Confidence: |calibrated - 0.5| * 2 * rolling_accuracy
    """

    def __init__(
        self,
        a: float = -1.0,
        b: float = 0.0,
        rolling_window: int = 100,
    ):
        self.a = a
        self.b = b
        self._rolling_window = rolling_window
        self._outcomes: deque[bool] = deque(maxlen=rolling_window)
        self._lock = threading.Lock()

    def calibrate(self, raw_probability: float) -> float:
        """Apply Platt scaling to a raw probability.

        Args:
            raw_probability: Model output probability (0.0-1.0).

        Returns:
            Calibrated probability (0.0-1.0).
        """
        logit = self.a * raw_probability + self.b
        # Clamp to avoid overflow
        logit = max(min(logit, 50.0), -50.0)
        return 1.0 / (1.0 + math.exp(logit))

    def calibrate_batch(self, raw_probabilities: np.ndarray) -> np.ndarray:
        """Apply Platt scaling to an array of raw probabilities.

        Args:
            raw_probabilities: Array of model output probabilities.

        Returns:
            Array of calibrated probabilities.
        """
        logits = self.a * raw_probabilities + self.b
        logits = np.clip(logits, -50.0, 50.0)
        return 1.0 / (1.0 + np.exp(logits))

    def fit(
        self,
        raw_probabilities: np.ndarray,
        y_true: np.ndarray,
        learning_rate: float = 0.01,
        max_iter: int = 1000,
    ) -> tuple[float, float]:
        """Fit Platt scaling parameters using gradient descent.

        Minimizes negative log-likelihood:
        NLL = -sum(y * log(p) + (1-y) * log(1-p))
        where p = sigmoid(a * raw + b).

        Args:
            raw_probabilities: Model output probabilities for test set.
            y_true: Actual binary labels (0/1).
            learning_rate: SGD learning rate.
            max_iter: Maximum iterations.

        Returns:
            Tuple of (a, b) fitted parameters.
        """
        a, b = self.a, self.b
        n = len(raw_probabilities)
        if n == 0:
            return a, b

        raw = np.asarray(raw_probabilities, dtype=np.float64)
        y = np.asarray(y_true, dtype=np.float64)

        for _ in range(max_iter):
            logits = a * raw + b
            logits = np.clip(logits, -50.0, 50.0)
            p = 1.0 / (1.0 + np.exp(logits))

            # Gradients
            error = p - y
            grad_a = np.dot(error, raw) / n
            grad_b = np.mean(error)

            a -= learning_rate * grad_a
            b -= learning_rate * grad_b

            # Convergence check
            if abs(grad_a) < 1e-7 and abs(grad_b) < 1e-7:
                break

        self.a = float(a)
        self.b = float(b)
        logger.info("Calibration fitted: a=%.6f, b=%.6f", self.a, self.b)
        return self.a, self.b

    def record_outcome(self, predicted_up: bool, actual_up: bool) -> None:
        """Record a prediction outcome for rolling accuracy tracking.

        Args:
            predicted_up: Whether the model predicted up.
            actual_up: Whether the actual outcome was up.
        """
        with self._lock:
            self._outcomes.append(predicted_up == actual_up)

    def rolling_accuracy(self) -> float:
        """Get rolling accuracy over the window.

        Returns:
            Accuracy (0.0-1.0), or 0.5 if no outcomes recorded.
        """
        with self._lock:
            if not self._outcomes:
                return 0.5
            return sum(self._outcomes) / len(self._outcomes)

    def confidence(self, calibrated_probability: float) -> float:
        """Compute confidence score.

        Formula: |calibrated - 0.5| * 2 * rolling_accuracy

        Args:
            calibrated_probability: Calibrated probability (0.0-1.0).

        Returns:
            Confidence score (0.0-1.0).
        """
        deviation = abs(calibrated_probability - 0.5) * 2
        return min(deviation * self.rolling_accuracy(), 1.0)

    def needs_recalibration(self, min_samples: int = 50, min_accuracy: float = 0.52) -> bool:
        """Check if the model needs recalibration.

        Returns True if rolling accuracy drops below min_accuracy
        with at least min_samples outcomes recorded.
        """
        with self._lock:
            if len(self._outcomes) < min_samples:
                return False
            acc = sum(self._outcomes) / len(self._outcomes)
            return acc < min_accuracy

    def outcome_count(self) -> int:
        """Number of outcomes recorded in the rolling window."""
        with self._lock:
            return len(self._outcomes)

    def save(self, path: Path) -> None:
        """Save calibration parameters to JSON file.

        Args:
            path: Path to calibration.json file.
        """
        data = {
            "a": self.a,
            "b": self.b,
            "rolling_window": self._rolling_window,
            "rolling_accuracy": self.rolling_accuracy(),
            "outcome_count": self.outcome_count(),
        }
        path.write_text(json.dumps(data, indent=2))
        logger.info("Calibration saved to %s", path)

    @classmethod
    def load(cls, path: Path) -> "PredictionCalibrator":
        """Load calibration parameters from JSON file.

        Args:
            path: Path to calibration.json file.

        Returns:
            PredictionCalibrator instance.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        data = json.loads(path.read_text())
        return cls(
            a=data.get("a", -1.0),
            b=data.get("b", 0.0),
            rolling_window=data.get("rolling_window", 100),
        )
