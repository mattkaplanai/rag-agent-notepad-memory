Run the full test suite inside the Docker container and show a clean summary.

---

## Steps to execute

**Step 1 — Run all tests**

```bash
docker exec refund-gradio python -m pytest tests/ -v --tb=short 2>&1
```

**Step 2 — Display clearly:**
- Total passed / failed / error count
- List any failures with the test name and reason
- If all pass: "✓ All X tests passed"
- If failures: show each failed test name, what was expected vs actual, and a suggested fix

**Step 3 — If the container is not running:**

Say: "Container is not running. Start it with: `docker compose up -d`"
