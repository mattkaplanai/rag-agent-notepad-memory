Run the tests/ folder inside the Docker container and show a clean summary.

An optional argument can filter which tests to run (e.g. `test_api`, `test_integration`, `test_guards`).
If no argument is given, run all tests.

---

## Steps to execute

**Step 1 — Build the test command**

- Docker binary is at `/Applications/Docker.app/Contents/Resources/bin/docker`
- Container name: `refund-gradio`
- If an argument was provided (e.g. `/run-tests test_api`), run only that file:
  ```bash
  /Applications/Docker.app/Contents/Resources/bin/docker exec refund-gradio python -m pytest tests/test_<arg>.py -v --tb=short 2>&1
  ```
- If no argument, run the full suite:
  ```bash
  /Applications/Docker.app/Contents/Resources/bin/docker exec refund-gradio python -m pytest tests/ -v --tb=short 2>&1
  ```

**Step 2 — If the container is not running:**

Say: "Container is not running. Start it with: `/Applications/Docker.app/Contents/Resources/bin/docker compose up -d`"

**Step 3 — Display a clean summary:**

- Total passed / failed / error count
- If all pass: "✓ All X tests passed"
- If failures: for each failed test show:
  - Test name
  - What was expected vs actual
  - A one-line suggested fix
