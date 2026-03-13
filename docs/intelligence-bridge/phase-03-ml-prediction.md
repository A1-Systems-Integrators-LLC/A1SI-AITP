# Phase 3: ML Prediction Service & Feedback Loop

## Scope

Enhance `common/ml/` with real-time prediction, calibration, ensemble, and feedback tracking.

## New Files

| File | Class/Function | Description |
|------|---------------|-------------|
| `common/ml/prediction.py` | `PredictionResult`, `PredictionService` | Real-time prediction with model selection cascade |
| `common/ml/calibration.py` | `PredictionCalibrator` | Platt scaling, rolling accuracy, confidence formula |
| `common/ml/ensemble.py` | `ModelEnsemble` | Multi-model ensemble (3 modes) |
| `common/ml/feedback.py` | `FeedbackTracker` | Outcome tracking, retrain triggers, JSONL storage |

## Modified Files

| File | Change |
|------|--------|
| `common/ml/features.py` | Add regime/sentiment/temporal/volatility features (~55→70) |
| `common/ml/trainer.py` | Add `fit_calibration=True` param, save calibration to manifest |
| `common/ml/__init__.py` | Export all new classes |

## Tests

Target: ~150 new tests in `backend/tests/test_ml_phase3.py`

## Status: IN PROGRESS
