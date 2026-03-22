"""LangFuse cloud observability — drop-in helpers with graceful no-op fallback.

Usage:
  - Decorate the top-level pipeline function with @observe_pipeline
  - Add get_langfuse_callback() to LangChain agent callbacks
  - Use get_langfuse_anthropic_client() instead of anthropic.Anthropic() in
    native SDK calls so they appear as child spans inside the root trace.

All three helpers are safe no-ops when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
are not set — no imports fail, no warnings are raised.
"""

import logging
import os

logger = logging.getLogger(__name__)

LANGFUSE_ENABLED = bool(
    os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    and os.getenv("LANGFUSE_SECRET_KEY", "").strip()
)

# Normalise host: SDK reads LANGFUSE_HOST; also accept LANGFUSE_BASE_URL alias
_host = (
    os.getenv("LANGFUSE_HOST")
    or os.getenv("LANGFUSE_BASE_URL")
    or "https://cloud.langfuse.com"
)
if LANGFUSE_ENABLED:
    os.environ["LANGFUSE_HOST"] = _host  # ensure SDK picks up the right value
    logger.info("LangFuse observability enabled — host: %s", _host)


def observe_pipeline(func):
    """Wrap a function with a LangFuse root trace. No-op if LangFuse is disabled."""
    if not LANGFUSE_ENABLED:
        return func
    try:
        # Langfuse v3: observe is at the top-level package
        from langfuse import observe

        return observe(name="refund-pipeline")(func)
    except Exception as exc:
        logger.warning("LangFuse observe decorator unavailable: %s", exc)
        return func


def get_langfuse_callback():
    """Return the current LangFuse LangChain callback handler, or None."""
    if not LANGFUSE_ENABLED:
        return None
    try:
        # Langfuse v3: LangChain handler is in langfuse.langchain
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:
        return None


def get_langfuse_anthropic_client():
    """Return a plain Anthropic client. LangFuse v3 instruments via OTEL, not a wrapper."""
    import anthropic

    return anthropic.Anthropic()
