"""Local inference bundle for the ETA revision models (docs/model_serving.md).

The one supported entry point is `load_predictor(bundle_dir).predict(record)`.
"""

from bart_reliability.serving.predictor import BundleError, Predictor, RecordError, load_predictor

__all__ = ["BundleError", "Predictor", "RecordError", "load_predictor"]
