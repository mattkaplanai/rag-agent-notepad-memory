Query Langfuse traces and summarize token spend by agent for the last 50 traces.

---

## Steps to execute

**Step 1 — Fetch token usage from Langfuse**

Run this Python script inside the Docker container:

```bash
docker exec refund-gradio python - <<'EOF'
import os, json
from collections import defaultdict

try:
    from langfuse import get_client

    lf = get_client()

    traces = lf.api.trace.list(limit=50).data
    if not traces:
        print(json.dumps({"error": "no_traces"}))
    else:
        agent_tokens = defaultdict(lambda: {"input": 0, "output": 0, "total": 0, "calls": 0})
        grand = {"input": 0, "output": 0, "total": 0, "calls": 0}

        for trace in traces:
            observations = lf.api.observations.get_many(trace_id=trace.id).data
            for obs in observations:
                usage = getattr(obs, "usage", None)
                if usage is None:
                    continue
                name = obs.name or "unknown"
                inp = getattr(usage, "input", 0) or 0
                out = getattr(usage, "output", 0) or 0
                tot = getattr(usage, "total", 0) or (inp + out)
                agent_tokens[name]["input"] += inp
                agent_tokens[name]["output"] += out
                agent_tokens[name]["total"] += tot
                agent_tokens[name]["calls"] += 1
                grand["input"] += inp
                grand["output"] += out
                grand["total"] += tot
                grand["calls"] += 1

        print(json.dumps({"agents": dict(agent_tokens), "grand_total": grand, "traces_checked": len(traces)}))

except Exception as e:
    print(json.dumps({"error": str(e)}))
EOF
```

**Step 2 — Parse and display results**

If `error` is in the output:
- If `"no_traces"`: say "No traces found in Langfuse. Have you processed any cases?"
- If Langfuse keys are missing: say "Langfuse is not configured. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env"
- Otherwise show the error message.

If successful, display:

**Header:** "Token Usage — Last N traces"

**Table 1 — By Agent (sorted by total tokens desc):**
| Agent | Calls | Input Tokens | Output Tokens | Total Tokens |
|-------|-------|-------------|--------------|-------------|
| ... | ... | ... | ... | ... |

**Table 2 — Grand Total:**
| Input | Output | Total | Avg per trace |
|-------|--------|-------|--------------|
| ...   | ...    | ...   | ...           |

**Cost tip:** If any agent has a high total, note which model it uses (from config):
- `refund-pipeline` / `classifier` → claude-haiku-4-5 (cheapest)
- `researcher` → claude-sonnet-4-6 (most expensive)
- `analyst`, `writer`, `judge` → claude-sonnet-4-6

**Step 3 — If container is not running:**

Say: "Container is not running. Start it with: `docker compose up -d`"
