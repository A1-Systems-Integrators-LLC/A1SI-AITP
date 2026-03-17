"""LSTM Training Pipeline
========================
Trains LSTMPredictor on OHLCV feature sequences.
Supports early stopping, learning rate scheduling, and model checkpointing.

Requires: torch>=2.3
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import numpy as np
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    HAS_TORCH = True
    from common.ml.lstm_model import (
        DEFAULT_SEQ_LEN,
        LSTMConfig,
        LSTMPredictor,
        prepare_sequences,
    )
except ImportError:  # pragma: no cover
    HAS_TORCH = False
    np = None  # type: ignore[assignment]
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    DEFAULT_SEQ_LEN = 60  # type: ignore[assignment]
    LSTMConfig = None  # type: ignore[assignment, misc]
    LSTMPredictor = None  # type: ignore[assignment, misc]
    prepare_sequences = None  # type: ignore[assignment]

# ── Training defaults ─────────────────────────────────────────────────────────
DEFAULT_EPOCHS = 50
DEFAULT_BATCH_SIZE = 32
DEFAULT_LEARNING_RATE = 0.001
DEFAULT_PATIENCE = 7  # early stopping patience
DEFAULT_TEST_RATIO = 0.2


@dataclass
class TrainResult:
    """Result from LSTM training."""

    model: object  # LSTMPredictor
    metrics: dict  # accuracy, loss, etc.
    metadata: dict  # training params
    elapsed_seconds: float


def train_lstm(
    features: object,
    target: object,
    config: LSTMConfig | None = None,
    epochs: int = DEFAULT_EPOCHS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    patience: int = DEFAULT_PATIENCE,
    test_ratio: float = DEFAULT_TEST_RATIO,
    seq_len: int = DEFAULT_SEQ_LEN,
    save_path: Path | str | None = None,
) -> TrainResult:
    """Train an LSTM model on feature sequences.

    Args:
        features: DataFrame or numpy array (n_rows, n_features).
        target: Series or numpy array (n_rows,) binary 0/1.
        config: LSTMConfig override (input_size auto-detected if None).
        epochs: Maximum training epochs.
        batch_size: Mini-batch size.
        learning_rate: Initial learning rate.
        patience: Early stopping patience (epochs without improvement).
        test_ratio: Fraction of data for test set (chronological split).
        seq_len: Sequence length for LSTM input.
        save_path: Optional path to save best model checkpoint.

    Returns:
        TrainResult with model, metrics, metadata.
    """
    if not HAS_TORCH:
        raise ImportError("torch is required for LSTM training")

    start_time = time.monotonic()

    # Convert to numpy
    feat_arr = np.asarray(features, dtype=np.float32)
    tgt_arr = np.asarray(target, dtype=np.float32)

    n_features = feat_arr.shape[1]

    # Build config if not provided
    if config is None:
        config = LSTMConfig(input_size=n_features, seq_len=seq_len)

    # Prepare sequences
    x_all, y_all = prepare_sequences(feat_arr, tgt_arr, seq_len)
    n_samples = len(x_all)

    # Chronological train/test split
    split_idx = max(1, int(n_samples * (1 - test_ratio)))
    x_train, x_test = x_all[:split_idx], x_all[split_idx:]
    y_train, y_test = y_all[:split_idx], y_all[split_idx:]

    logger.info(
        "LSTM training: %d train, %d test sequences (%d features, seq_len=%d)",
        len(x_train), len(x_test), n_features, seq_len,
    )

    # DataLoader
    train_dataset = TensorDataset(x_train, y_train)
    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=False,  # keep temporal order
    )

    # Model
    model = LSTMPredictor(config)
    criterion = nn.BCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=3,
    )

    # Training loop with early stopping
    best_val_loss = float("inf")
    best_state = None
    epochs_no_improve = 0

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        n_batches = 0

        for x_batch, y_batch in train_loader:
            optimizer.zero_grad()
            output = model(x_batch)
            loss = criterion(output, y_batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_loss += loss.item()
            n_batches += 1

        avg_train_loss = train_loss / max(n_batches, 1)

        # Validation
        model.eval()
        with torch.no_grad():
            val_output = model(x_test)
            val_loss = criterion(val_output, y_test).item()

        scheduler.step(val_loss)

        # Early stopping
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1

        if (epoch + 1) % 10 == 0 or epoch == 0:
            logger.info(
                "Epoch %d/%d — train_loss=%.4f, val_loss=%.4f",
                epoch + 1, epochs, avg_train_loss, val_loss,
            )

        if epochs_no_improve >= patience:
            logger.info("Early stopping at epoch %d", epoch + 1)
            break

    # Load best model
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()

    # Compute test metrics
    with torch.no_grad():
        test_probs = model(x_test)
        test_preds = (test_probs >= 0.5).float()
        accuracy = float((test_preds == y_test).float().mean())
        test_loss = criterion(test_probs, y_test).item()

    # Directional metrics
    y_test_np = y_test.numpy().flatten()
    preds_np = test_preds.numpy().flatten()
    tp = float(((preds_np == 1) & (y_test_np == 1)).sum())
    fp = float(((preds_np == 1) & (y_test_np == 0)).sum())
    fn = float(((preds_np == 0) & (y_test_np == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    elapsed = time.monotonic() - start_time

    metrics = {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "test_loss": round(test_loss, 6),
        "best_val_loss": round(best_val_loss, 6),
        "train_rows": len(x_train),
        "test_rows": len(x_test),
        "n_features": n_features,
        "epochs_trained": epoch + 1,
    }

    metadata = {
        "model_type": "LSTM",
        "seq_len": seq_len,
        "hidden_size": config.hidden_size,
        "num_layers": config.num_layers,
        "dropout": config.dropout,
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "patience": patience,
    }

    # Save if requested
    if save_path is not None:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        model.save(save_path)

    logger.info(
        "LSTM training complete: accuracy=%.4f, f1=%.4f in %.1fs",
        accuracy, f1, elapsed,
    )

    return TrainResult(
        model=model,
        metrics=metrics,
        metadata=metadata,
        elapsed_seconds=round(elapsed, 2),
    )
