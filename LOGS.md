# How to see logs and debug errors

## 1. In the UI (after you see "Error")

- Open the **"🤖 Agent Log"** tab (next to "📄 Decision").
- The full error and **traceback** are shown there so you can see which line failed.
- The **"📄 Decision"** tab also shows the same error and traceback.

## 2. Log file (live stream)

Everything the app prints goes to **`logs/multi_agent.log`**.

**Watch it live** (in a second terminal while the app runs):

```bash
cd /Users/mehmetkaymak/Desktop/rag-agent-notepad-memory
tail -f logs/multi_agent.log
```

When you click "Run Multi-Agent Analysis" and something fails, the error and traceback are printed there too.

## 3. Terminal where the app runs

If you start the app in the foreground:

```bash
GRADIO_SERVER_PORT=7862 python multi_agent.py
```

you’ll see the same output (including errors) in that terminal.

## Quick checklist when you see "Error"

1. Check the **Agent Log** tab in the browser for the traceback.
2. Run `tail -f logs/multi_agent.log` and submit again; the error will appear in that file.
3. If the app is running in a terminal, look at that terminal for the same error.
