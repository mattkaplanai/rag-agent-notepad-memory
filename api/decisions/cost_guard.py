"""
Daily LLM cost ceiling guard.

HOW IT WORKS:
  - After each full pipeline run, we add COST_PER_PIPELINE_RUN_USD to a
    Redis counter keyed by today's date (e.g. "daily_cost:2026-03-22").
  - The key auto-expires at midnight so the counter resets daily.
  - Before dispatching a new pipeline job, the view calls is_halted() to
    check if the ceiling has been reached.
  - At 80% of the ceiling, a WARNING is logged so you can act before it stops.
  - If Redis is down, we fail open (don't block requests) and log the error.

COST ESTIMATE per full pipeline run (conservative):
  - Claude Haiku (classifier):        ~$0.001
  - Claude Sonnet x4 agents:          ~$0.04
  - OpenAI text-embedding-3-small:    ~$0.001
  ─────────────────────────────────────────────
  Total default estimate:             ~$0.05 / run

Override via env vars:
  DAILY_COST_LIMIT_USD        (default: 10.0)
  COST_PER_PIPELINE_RUN_USD   (default: 0.05)
"""

import logging
import os
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

DAILY_COST_LIMIT_USD = float(os.getenv("DAILY_COST_LIMIT_USD", "10.0"))
COST_PER_PIPELINE_RUN_USD = float(os.getenv("COST_PER_PIPELINE_RUN_USD", "0.05"))
_WARN_AT_PCT = 0.80  # warn at 80% of limit


def _redis():
    import redis as redis_lib
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    return redis_lib.from_url(redis_url, decode_responses=True)


def _today_key() -> str:
    return f"daily_cost:{date.today().isoformat()}"


def _seconds_until_midnight() -> int:
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    return int((midnight - now).total_seconds()) + 1


def get_daily_spend() -> float:
    """Return today's accumulated estimated spend in USD."""
    try:
        val = _redis().get(_today_key())
        return float(val) if val else 0.0
    except Exception as exc:
        logger.error("Cost guard — Redis read error: %s", exc)
        return 0.0


def record_pipeline_cost() -> float:
    """
    Add one pipeline run to today's cost counter.
    Returns the new daily total.
    Called by the Celery task after every successful pipeline run.
    """
    try:
        r = _redis()
        key = _today_key()
        new_total = float(r.incrbyfloat(key, COST_PER_PIPELINE_RUN_USD))
        # Set TTL only if this is the first write today
        if r.ttl(key) < 0:
            r.expire(key, _seconds_until_midnight())

        if new_total >= DAILY_COST_LIMIT_USD:
            logger.error(
                "COST CEILING HIT: $%.4f spent today (limit $%.2f) — pipeline halted until midnight UTC",
                new_total, DAILY_COST_LIMIT_USD,
            )
        elif new_total >= DAILY_COST_LIMIT_USD * _WARN_AT_PCT:
            logger.warning(
                "COST ALERT: $%.4f spent today = %.0f%% of $%.2f daily limit",
                new_total, (new_total / DAILY_COST_LIMIT_USD) * 100, DAILY_COST_LIMIT_USD,
            )
        else:
            logger.info("Cost tracker: $%.4f / $%.2f today", new_total, DAILY_COST_LIMIT_USD)

        return new_total
    except Exception as exc:
        logger.error("Cost guard — Redis write error: %s", exc)
        return 0.0


def is_halted() -> bool:
    """
    Return True if today's spend has reached DAILY_COST_LIMIT_USD.
    Fails open (returns False) if Redis is unreachable — cost ceiling
    should not take down the service if the counter is unavailable.
    """
    try:
        spend = get_daily_spend()
        if spend >= DAILY_COST_LIMIT_USD:
            logger.warning(
                "Cost ceiling active: $%.4f / $%.2f — new pipeline jobs blocked",
                spend, DAILY_COST_LIMIT_USD,
            )
            return True
        return False
    except Exception as exc:
        logger.error("Cost guard — is_halted check error: %s", exc)
        return False  # fail open
