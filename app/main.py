"""
Airlines Refund Decision Maker -- Main Entry Point

Usage:
    python -m app.main
    # or
    python app/main.py
"""

import logging

from app.config import SERVER_HOST, SERVER_PORT, ensure_anthropic_or_fallback
from app.rag.indexer import build_or_load_index
from app.agents.researcher import build_researcher_parallel
from app.agents.analyst import build_analyst
from app.agents.writer import build_writer
from app.ui.gradio_app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Airlines Refund Decision Maker")
    logger.info("Building document index...")
    index = build_or_load_index()

    ensure_anthropic_or_fallback(logger)

    logger.info("Building worker agents...")
    researcher_agent = build_researcher_parallel(index)
    analyst_agent = build_analyst()
    writer_agent = build_writer()

    logger.info("Creating UI...")
    app = create_app(index, researcher_agent, analyst_agent, writer_agent)

    logger.info("Ready. Launching on %s:%d", SERVER_HOST, SERVER_PORT)
    app.launch(server_name=SERVER_HOST, server_port=SERVER_PORT)


if __name__ == "__main__":
    main()
