Deploy the app, submit 3 representative test cases back-to-back, then check the DB for the results — in one command.

---

## Steps to execute

### Step 1 — Deploy

Run: `docker compose up --build -d`

Wait up to 30s for the Gradio service to return HTTP 200:
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:7861/
```
If it doesn't come up, stop and show: `docker logs --tail 20 refund-gradio`

---

### Step 2 — Submit 3 test cases (sequentially)

For each case, generate a unique `session_hash`, submit via the Gradio queue API, wait **70 seconds**, then poll for the result.

Use this submit pattern (replace DESCRIPTION and SESSION):
```bash
SESSION="smoke$(python3 -c "import random,string; print(''.join(random.choices(string.ascii_lowercase+string.digits,k=6)))")"
curl -s -X POST "http://localhost:7861/gradio_api/queue/join" \
  -H "Content-Type: application/json" \
  -d "{\"fn_index\":0,\"data\":[\"CASE_TYPE\",\"FLIGHT_TYPE\",\"TICKET_TYPE\",\"PAYMENT_METHOD\",\"ALTERNATIVE\",\"DESCRIPTION\"],\"session_hash\":\"$SESSION\"}"
echo "SESSION=$SESSION"
```

Then poll:
```bash
curl -s "http://localhost:7861/gradio_api/queue/data?session_hash=SESSION" --max-time 15
```

Find the line with `"process_completed"` in the SSE stream and extract `output.data[0]`.

**Run all 3 cases one at a time. Do NOT run them in parallel.**

---

#### Case 1 — Should be APPROVED (long domestic delay, DOT threshold exceeded)
```
case_type:   "Schedule Change / Significant Delay"
flight_type: "Domestic (within US)"
ticket_type: "Non-refundable"
payment:     "Credit Card"
alternative: "No — I did not accept any alternative"
description: "My United Airlines flight UA202 from New York to Los Angeles on March 10 was delayed 4 hours 45 minutes due to a crew shortage (not weather). The airline offered no compensation. Ticket price was $380. I am requesting a full refund under DOT regulations."
```

#### Case 2 — Should be DENIED (short delay under threshold)
```
case_type:   "Schedule Change / Significant Delay"
flight_type: "Domestic (within US)"
ticket_type: "Non-refundable"
payment:     "Credit Card"
alternative: "No — I did not accept any alternative"
description: "My Delta flight DL455 from Atlanta to Denver on March 12 was delayed 1 hour 20 minutes due to weather. I had to wait at the gate. Ticket price was $210. I want a refund."
```

#### Case 3 — Should be APPROVED (flight cancellation, no alternative accepted)
```
case_type:   "Flight Cancellation"
flight_type: "International"
ticket_type: "Non-refundable"
payment:     "Credit Card"
alternative: "No — I did not accept any alternative"
description: "American Airlines cancelled my flight AA901 from Miami to London on March 18, citing operational reasons. I was not offered a comparable alternative flight within 24 hours. Ticket price was $890. I declined their voucher offer and am requesting a cash refund per DOT automatic refund rules."
```

---

### Step 3 — Check DB for the 3 new decisions

Use the `mcp__refund-db__query` tool to run:

```sql
SELECT id, case_type, flight_type,
       result->>'decision' AS decision,
       result->>'confidence' AS confidence,
       created_at
FROM refund_decisions
ORDER BY created_at DESC
LIMIT 5;
```

---

### Step 4 — Display results

Show a summary table:

```
SMOKE TEST RESULTS
==================
Case 1 (Long delay / Domestic)       → DECISION  [confidence]  ✓ PASS / ✗ FAIL
Case 2 (Short delay under threshold)  → DECISION  [confidence]  ✓ PASS / ✗ FAIL
Case 3 (Cancellation / International) → DECISION  [confidence]  ✓ PASS / ✗ FAIL

DB check: X of 3 cases found in database.

Overall: PASS / FAIL
```

Pass/fail criteria:
- Case 1 passes if decision is `APPROVED` or `PARTIAL`
- Case 2 passes if decision is `DENIED`
- Case 3 passes if decision is `APPROVED` or `PARTIAL`
- DB check passes if all 3 cases appear in the last 5 rows

If any case fails, show the full `output.data[0]` for that case and suggest: `docker logs --tail 30 refund-gradio`
