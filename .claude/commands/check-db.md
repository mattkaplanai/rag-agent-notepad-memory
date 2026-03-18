Query the refund PostgreSQL database and show a summary of decisions.

---

## Steps to execute

Use the `mcp__refund-db__query` tool to run these queries in order:

**Query 1 — Overall summary**
```sql
SELECT
    decision,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
FROM refund_decisions
GROUP BY decision
ORDER BY count DESC;
```

**Query 2 — By case type**
```sql
SELECT
    case_type,
    COUNT(*) AS total,
    SUM(CASE WHEN result->>'decision' = 'APPROVED' THEN 1 ELSE 0 END) AS approved,
    SUM(CASE WHEN result->>'decision' = 'DENIED' THEN 1 ELSE 0 END) AS denied,
    SUM(CASE WHEN result->>'decision' = 'PARTIAL' THEN 1 ELSE 0 END) AS partial
FROM refund_decisions
GROUP BY case_type
ORDER BY total DESC;
```

**Query 3 — Recent 5 decisions**
```sql
SELECT id, case_type, flight_type, result->>'decision' AS decision,
       result->>'confidence' AS confidence, created_at
FROM refund_decisions
ORDER BY created_at DESC
LIMIT 5;
```

**Display as:**
- A headline: "Refund DB — X total decisions"
- Decision breakdown table (APPROVED / DENIED / PARTIAL with %)
- Case type breakdown table
- Recent 5 decisions list
