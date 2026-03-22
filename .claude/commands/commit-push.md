Commit all staged and unstaged changes, then push to the current remote branch.

Optional: pass a commit message as an argument, e.g. `/commit-push "fix: correct refund calculation"`
If no message is provided, auto-generate one from the diff.

**Argument:** $ARGUMENTS (optional commit message)

---

## Steps to execute

**Step 1 — Check current state**

Run these in parallel:
```bash
git status
```
```bash
git diff --stat
```
```bash
git log --oneline -3
```

If there are no changes (clean working tree and nothing staged), say:
"Nothing to commit — working tree is clean." and stop.

**Step 2 — Stage all changes**

```bash
git add -A
```

**Step 3 — Determine commit message**

- If `$ARGUMENTS` is provided and non-empty: use it as the commit message.
- If `$ARGUMENTS` is empty: read `git diff --cached --stat` and `git diff --cached --name-only`, then write a concise 1-sentence commit message that summarizes what changed. Follow the style of recent commits (check `git log --oneline -5`).

**Step 4 — Commit**

```bash
git commit -m "<message>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

If the commit fails (e.g. pre-commit hook), show the error and stop. Do not force.

**Step 5 — Push**

```bash
git push origin HEAD
```

**Step 6 — Display result**

Show:
- The commit hash and message
- The branch and remote it was pushed to
- How many files changed
- A link hint: "View on GitHub: check your repo's branch `<branch-name>`"

If push fails (e.g. rejected), show the error and suggest: "Run `/deploy` first if you need to resolve conflicts, or check if the remote branch has diverged."
