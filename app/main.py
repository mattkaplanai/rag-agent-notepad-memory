"""
Airlines Refund Decision Maker — Main Entry Point

Usage:
    python -m app.main
    # or
    python app/main.py
"""

from app.config import SERVER_HOST, SERVER_PORT
from app.rag.indexer import build_or_load_index
from app.agents.researcher import build_researcher
from app.agents.analyst import build_analyst
from app.agents.writer import build_writer
from app.ui.gradio_app import create_app


def main():
    print("[APP] Airlines Refund Decision Maker")
    print("[APP] Building document index...")
    index = build_or_load_index()

    print("[APP] Building worker agents...")
    researcher_agent = build_researcher(index)
    analyst_agent = build_analyst()
    writer_agent = build_writer()

    print("[APP] Creating UI...")
    app = create_app(index, researcher_agent, analyst_agent, writer_agent)

    print(f"[APP] Ready. Launching on {SERVER_HOST}:{SERVER_PORT}")
    app.launch(server_name=SERVER_HOST, server_port=SERVER_PORT)


if __name__ == "__main__":
    main()
