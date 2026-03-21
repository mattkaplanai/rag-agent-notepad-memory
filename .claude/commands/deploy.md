Rebuild and restart the Docker services. Use when code changes need to be deployed locally.

**Mode:** $ARGUMENTS (optional: "full" to rebuild from scratch, default is fast restart)

---

## Steps to execute

**Step 1 — Determine mode**

- If argument is "full": rebuild with no cache (`--no-cache`)
- Otherwise: standard rebuild

**Step 2 — Rebuild and restart**

Standard (default):
```bash
docker compose up --build -d
```

Full rebuild (when dependencies changed, e.g. requirements.txt):
```bash
docker compose build --no-cache && docker compose up -d
```

**Step 3 — Wait and verify (check every 5s, up to 30s)**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:7861/
```

Repeat until 200 or timeout.

**Step 4 — Show status**

```bash
docker compose ps
```

**Step 5 — Display:**
- Whether deploy succeeded or failed
- Which services are running and their ports
- If failed: show last 20 lines of logs with `docker logs --tail 20 refund-gradio`
- Remind: if you changed `OPENAI_EMBEDDING_MODEL`, run `docker compose run --rm gradio python scripts/clear_decision_data.py` first
