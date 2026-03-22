"""
Celery application for the refund decision pipeline.

HOW CELERY WORKS:
  1. Your Django view calls  task.delay(data)  — this is non-blocking.
     It puts a message (the job) into the Redis queue and returns a task_id instantly.
  2. The Celery worker (a separate process) is always listening to Redis.
     It picks up the job, runs the function, and stores the result back in Redis.
  3. Your frontend polls  GET /api/v1/jobs/{task_id}/  every 2 seconds.
     Django checks AsyncResult(task_id).state → PENDING → STARTED → SUCCESS.
  4. When SUCCESS, the result is read from Redis and returned to the browser.

CELERY_BROKER_URL:  where jobs are sent  (Redis, queue = message broker)
CELERY_RESULT_BACKEND: where results are stored (also Redis)
"""

import os
from celery import Celery

# Tell Django which settings module to use
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api_project.settings')

app = Celery('api_project')

# Read all CELERY_* settings from Django's settings.py
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all INSTALLED_APPS
# Celery will look for a  tasks.py  file in each app (e.g. decisions/tasks.py)
app.autodiscover_tasks()
