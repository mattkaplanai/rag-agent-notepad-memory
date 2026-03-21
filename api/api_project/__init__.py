# This makes the Celery app available as a Django app-level import.
# Required for @shared_task decorator to work correctly.
from .celery import app as celery_app  # noqa: F401

__all__ = ('celery_app',)
