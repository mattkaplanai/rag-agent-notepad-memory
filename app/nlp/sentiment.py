"""Sentiment analysis for passenger descriptions.

Uses distilbert-base-uncased-finetuned-sst-2-english (HuggingFace) to detect
passenger frustration level from free-text descriptions.

Model is loaded once (lazy singleton) — not at import time, to avoid slowing
down the container startup before the first request arrives.

Frustration mapping:
  NEGATIVE + score >= 0.90  → HIGH   (clearly upset passenger)
  NEGATIVE + score >= 0.65  → MEDIUM (some negative tone)
  POSITIVE or low NEGATIVE  → LOW    (neutral / calm)
"""

import logging

logger = logging.getLogger(__name__)

_MODEL_NAME = "distilbert-base-uncased-finetuned-sst-2-english"

# Lazy singleton — initialized on first call to analyze_sentiment()
_sentiment_pipeline = None


def _get_pipeline():
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        from transformers import pipeline
        logger.info("[NLP] Loading sentiment model: %s", _MODEL_NAME)
        _sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model=_MODEL_NAME,
            truncation=True,
            max_length=512,
        )
        logger.info("[NLP] Sentiment model ready.")
    return _sentiment_pipeline


def analyze_sentiment(text: str) -> str:
    """Return frustration level: 'HIGH', 'MEDIUM', or 'LOW'.

    Falls back to 'LOW' if the model is unavailable or text is empty.
    """
    if not text or not text.strip():
        return "LOW"

    try:
        pipe = _get_pipeline()
        result = pipe(text[:512])[0]   # truncate to model max length
        label = result["label"]        # "POSITIVE" or "NEGATIVE"
        score = result["score"]        # confidence 0.0 – 1.0

        if label == "NEGATIVE":
            if score >= 0.90:
                return "HIGH"
            if score >= 0.65:
                return "MEDIUM"

        return "LOW"

    except Exception as exc:
        logger.warning("[NLP] Sentiment analysis failed (%s) — defaulting to LOW", exc)
        return "LOW"
