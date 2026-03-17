"""FinBERT financial sentiment analysis — ProsusAI/finbert via HuggingFace.

Lazy-loaded singleton (~440MB model, ~2GB RAM). Thread-safe.
CPU inference: ~100-300ms per text. Batch scoring for efficiency.

Requires: transformers>=4.40, torch>=2.3 (CPU-only OK).
"""

import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_model_lock = threading.Lock()
_pipeline = None
_load_attempted = False

BATCH_SIZE = 8
MAX_TEXT_LENGTH = 512  # FinBERT max token input


@dataclass
class FinBERTResult:
    """Single text sentiment result from FinBERT."""

    text: str
    label: str  # "positive", "negative", "neutral"
    score: float  # confidence 0-1
    sentiment: float  # mapped to [-1, 1]


def _load_pipeline():
    """Lazy-load the FinBERT pipeline. Thread-safe, loads only once."""
    global _pipeline, _load_attempted

    with _model_lock:
        if _pipeline is not None:
            return _pipeline
        if _load_attempted:
            return None

        _load_attempted = True

        try:
            from transformers import pipeline

            logger.info("Loading FinBERT model (ProsusAI/finbert)...")
            _pipeline = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                tokenizer="ProsusAI/finbert",
                device=-1,  # CPU
                truncation=True,
                max_length=MAX_TEXT_LENGTH,
            )
            logger.info("FinBERT model loaded successfully")
            return _pipeline
        except Exception as e:
            logger.warning("Failed to load FinBERT: %s", e)
            return None


def is_available() -> bool:
    """Check if FinBERT can be loaded (dependencies installed)."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def is_loaded() -> bool:
    """Check if FinBERT model is currently loaded in memory."""
    return _pipeline is not None


def _map_label_to_score(label: str, confidence: float) -> float:
    """Map FinBERT label + confidence to [-1, 1] sentiment score.

    FinBERT outputs: "positive", "negative", "neutral" with confidence.
    """
    if label == "positive":
        return confidence
    elif label == "negative":
        return -confidence
    else:
        return 0.0


def score_text(text: str) -> FinBERTResult | None:
    """Score a single text using FinBERT.

    Returns FinBERTResult or None if model unavailable.
    """
    pipe = _load_pipeline()
    if pipe is None:
        return None

    try:
        # Truncate to avoid tokenizer issues
        truncated = text[:MAX_TEXT_LENGTH * 4]  # ~4 chars per token estimate
        result = pipe(truncated)[0]
        label = result["label"]
        confidence = result["score"]

        return FinBERTResult(
            text=text[:100],
            label=label,
            score=confidence,
            sentiment=_map_label_to_score(label, confidence),
        )
    except Exception as e:
        logger.warning("FinBERT scoring failed: %s", e)
        return None


def score_batch(texts: list[str]) -> list[FinBERTResult | None]:
    """Score multiple texts in batches for efficiency.

    Returns list of FinBERTResult (or None for failed items).
    """
    pipe = _load_pipeline()
    if pipe is None:
        return [None] * len(texts)

    results: list[FinBERTResult | None] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        truncated = [t[:MAX_TEXT_LENGTH * 4] for t in batch]

        try:
            outputs = pipe(truncated)
            for text, output in zip(batch, outputs, strict=True):
                label = output["label"]
                confidence = output["score"]
                results.append(FinBERTResult(
                    text=text[:100],
                    label=label,
                    score=confidence,
                    sentiment=_map_label_to_score(label, confidence),
                ))
        except Exception as e:
            logger.warning("FinBERT batch scoring failed: %s", e)
            results.extend([None] * len(batch))

    return results


def score_article(title: str, summary: str = "") -> tuple[float, str]:
    """Score an article using FinBERT, matching scorer.py interface.

    Returns (score, label) where score in [-1, 1].
    Falls back to (0.0, "neutral") if model unavailable.
    """
    title_result = score_text(title)
    if title_result is None:
        return 0.0, "neutral"

    if summary:
        summary_result = score_text(summary)
        if summary_result is not None:
            combined = title_result.sentiment * 0.6 + summary_result.sentiment * 0.4
        else:
            combined = title_result.sentiment
    else:
        combined = title_result.sentiment

    combined = max(-1.0, min(1.0, combined))

    if combined > 0.1:
        label = "positive"
    elif combined < -0.1:
        label = "negative"
    else:
        label = "neutral"

    return round(combined, 4), label


def reset():
    """Reset the loaded model (for testing)."""
    global _pipeline, _load_attempted
    with _model_lock:
        _pipeline = None
        _load_attempted = False
