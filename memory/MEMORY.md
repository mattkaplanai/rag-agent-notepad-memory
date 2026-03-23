# Project Memory

## Workflow

- Solo project — push directly to `main`, no PRs needed
- Docker Compose service names: `django-api`, `celery-worker`, `frontend`, `gradio`, `redis`, `postgres`
- Always rebuild from `/Users/mehmetkaymak/Desktop/rag-agent-notepad-memory` (main project dir), not the worktree

## Key facts

- Frontend runs on port 3000 (React + nginx), Gradio on 7861, Django API on 8000
- nginx config is at `frontend/nginx.conf` — must rebuild `frontend` service after changes
- `django-api` needs `REDIS_URL: redis://redis:6379` in docker-compose to reach Redis by container name
- Rate limiting: Layer 1 = nginx (2 req/sec on /analyze/), Layer 2 = django-ratelimit (10 req/min), Layer 3 = cost_guard.py ($10/day ceiling via Redis)
