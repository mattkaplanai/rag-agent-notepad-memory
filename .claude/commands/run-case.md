Submit a test refund case to the local Gradio app at localhost:7861 and show the result.

**Case description to use:** $ARGUMENTS

If no argument was given, use this default case:
> "My United Airlines flight UA789 from Chicago to Miami on March 15 was delayed 5 hours 30 minutes due to crew scheduling issue (not weather). No compensation offered. Ticket cost $295. Requesting full refund under DOT regulations."

---

## Steps to execute

**Step 1 — Check the app is running**

Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:7861/`

If not 200, stop and say: "App is not running. Start it with: `docker compose up -d`"

**Step 2 — Submit the case**

Run this bash command (replace DESCRIPTION with the case description, escape $ as \$):

```bash
SESSION="skill$(python3 -c "import random,string; print(''.join(random.choices(string.ascii_lowercase+string.digits,k=6)))")"
curl -s -X POST "http://localhost:7861/gradio_api/queue/join" \
  -H "Content-Type: application/json" \
  -d "{\"fn_index\":0,\"data\":[\"Schedule Change / Significant Delay\",\"Domestic (within US)\",\"Non-refundable\",\"Credit Card\",\"No — I did not accept any alternative\",\"DESCRIPTION\"],\"session_hash\":\"$SESSION\"}"
echo "SESSION=$SESSION"
```

**Step 3 — Wait 70 seconds, then poll for result**

```bash
curl -s "http://localhost:7861/gradio_api/queue/data?session_hash=SESSION" --max-time 15
```

Find the line with `"process_completed"` in the SSE stream and extract `output.data[0]`.

**Step 4 — Display clearly:**
- DECISION: APPROVED / DENIED / PARTIAL
- Confidence level
- Key reasons (bullet points)
- Refund amount if APPROVED
- Whether Judge overrode the Writer's decision
- Total pipeline time

If there's an error, show it and suggest: `docker logs --tail 30 refund-gradio`
