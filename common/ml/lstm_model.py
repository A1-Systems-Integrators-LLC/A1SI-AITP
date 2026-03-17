"""LSTM Time Series Predictor
============================
2-layer LSTM network for directional probability prediction.
Takes 60-bar sequences of key features, outputs P(up) in [0, 1].

Requires: torch>=2.3
"""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn

    HAS_TORCH = True
except ImportError:  # pragma: no cover
    HAS_TORCH = False
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_SEQ_LEN = 60  # bars per input sequence
DEFAULT_HIDDEN_SIZE = 64
DEFAULT_NUM_LAYERS = 2
DEFAULT_DROPOUT = 0.2


@dataclass
class LSTMConfig:
    """Configuration for the LSTM model."""

    input_size: int  # number of features per bar
    hidden_size: int = DEFAULT_HIDDEN_SIZE
    num_layers: int = DEFAULT_NUM_LAYERS
    dropout: float = DEFAULT_DROPOUT
    seq_len: int = DEFAULT_SEQ_LEN


def is_available() -> bool:
    """Check if torch is available for LSTM inference."""
    return HAS_TORCH


class LSTMPredictor(nn.Module if HAS_TORCH else object):  # type: ignore[misc]
    """2-layer LSTM → Dense → Sigmoid for directional prediction.

    Input shape:  (batch_size, seq_len, input_size)
    Output shape: (batch_size, 1) — probability of upward move.
    """

    def __init__(self, config: LSTMConfig):
        if not HAS_TORCH:
            raise ImportError("torch is required for LSTMPredictor")
        super().__init__()
        self.config = config
        self.lstm = nn.LSTM(
            input_size=config.input_size,
            hidden_size=config.hidden_size,
            num_layers=config.num_layers,
            dropout=config.dropout if config.num_layers > 1 else 0.0,
            batch_first=True,
        )
        self.dropout = nn.Dropout(config.dropout)
        self.fc = nn.Linear(config.hidden_size, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        """Forward pass.

        Args:
            x: Input tensor of shape (batch, seq_len, input_size).

        Returns:
            Probability tensor of shape (batch, 1).
        """
        # LSTM output: (batch, seq_len, hidden_size)
        lstm_out, _ = self.lstm(x)
        # Take last timestep
        last_hidden = lstm_out[:, -1, :]
        out = self.dropout(last_hidden)
        out = self.fc(out)
        return self.sigmoid(out)

    def predict_proba(self, x: "torch.Tensor") -> float:
        """Single prediction probability (no grad).

        Args:
            x: Input tensor of shape (1, seq_len, input_size).

        Returns:
            Probability of upward move (float 0.0-1.0).
        """
        self.eval()
        with torch.no_grad():
            prob = self.forward(x)
        return float(prob.item())

    def save(self, path: Path | str) -> None:
        """Save model state dict to .pt file."""
        path = Path(path)
        torch.save(
            {
                "state_dict": self.state_dict(),
                "config": {
                    "input_size": self.config.input_size,
                    "hidden_size": self.config.hidden_size,
                    "num_layers": self.config.num_layers,
                    "dropout": self.config.dropout,
                    "seq_len": self.config.seq_len,
                },
            },
            path,
        )
        logger.info("LSTM model saved to %s", path)

    @classmethod
    def load(cls, path: Path | str) -> "LSTMPredictor":
        """Load model from .pt file."""
        if not HAS_TORCH:
            raise ImportError("torch is required to load LSTM models")
        path = Path(path)
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        config = LSTMConfig(**checkpoint["config"])
        model = cls(config)
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        logger.info("LSTM model loaded from %s", path)
        return model


def prepare_sequences(
    features: "object",
    target: "object",
    seq_len: int = DEFAULT_SEQ_LEN,
) -> tuple["torch.Tensor", "torch.Tensor"]:
    """Convert feature matrix + target into LSTM-ready sequences.

    Args:
        features: DataFrame or numpy array of shape (n_rows, n_features).
        target: Series or numpy array of shape (n_rows,).
        seq_len: Length of each input sequence.

    Returns:
        Tuple of (X_sequences, y_targets) as torch tensors.
        X shape: (n_samples, seq_len, n_features)
        y shape: (n_samples, 1)
    """
    if not HAS_TORCH:
        raise ImportError("torch is required for prepare_sequences")

    import numpy as np

    # Convert to numpy if needed
    feat_arr = np.asarray(features, dtype=np.float32)
    tgt_arr = np.asarray(target, dtype=np.float32)

    n_rows = len(feat_arr)
    if n_rows <= seq_len:
        raise ValueError(
            f"Need more than {seq_len} rows for sequences, got {n_rows}"
        )

    x_sequences = []
    y_targets = []
    for i in range(seq_len, n_rows):
        x_sequences.append(feat_arr[i - seq_len:i])
        y_targets.append(tgt_arr[i])

    x_tensor = torch.tensor(np.array(x_sequences), dtype=torch.float32)
    y_tensor = torch.tensor(np.array(y_targets), dtype=torch.float32).unsqueeze(1)

    return x_tensor, y_tensor
