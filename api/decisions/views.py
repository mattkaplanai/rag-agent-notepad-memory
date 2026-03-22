"""API views for the refund decision system."""

import logging

from django_ratelimit.decorators import ratelimit
from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from .models import RefundDecision
from .serializers import (
    RefundRequestSerializer,
    RefundDecisionSerializer,
    RefundDecisionListSerializer,
)


def _get_cache():
    from app.cache.decision_cache import DecisionCache
    return DecisionCache()


def _get_db():
    from app.db.decision_db import DecisionDB
    return DecisionDB()


@api_view(['GET'])
def health_check(request):
    """Health check endpoint."""
    return Response({
        "status": "healthy",
        "service": "Airlines Refund Decision API",
        "total_decisions": RefundDecision.objects.count(),
    })


@ratelimit(key='ip', rate='10/m', method='POST', block=False)
@api_view(['POST'])
def analyze_case(request):
    """
    Submit a refund case for analysis.

    HOW THIS WORKS NOW (async):
      1. Validate input + run input guard (fast, ~1s)
      2. Check cache tiers — if hit, return result immediately (fast)
      3. If no cache hit → dispatch Celery task → return 202 with job_id
      4. Frontend polls  GET /api/v1/jobs/{job_id}/  every 2 seconds
      5. When task completes, frontend reads the result from the job endpoint

    POST /api/v1/analyze/
    Body: {case_type, flight_type, ticket_type, payment_method, accepted_alternative, description}

    Returns (cache hit):  200  { source: "cache_...", result: {...} }
    Returns (async job):  202  { job_id: "uuid", status: "QUEUED" }
    """
    # django-ratelimit sets request.limited=True when IP exceeds 10 req/min
    if getattr(request, 'limited', False):
        return Response(
            {"error": "Too many requests. Limit: 10 per minute per IP."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    serializer = RefundRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    # Input guard: block unsafe or off-topic requests before queuing
    from app.guards import run_input_guard
    input_result = run_input_guard(data)
    if not input_result.passed:
        logger.warning("Input guard blocked request: %s", input_result.block_reason)
        return Response(
            input_result.block_response,
            status=status.HTTP_400_BAD_REQUEST,
        )
    data = input_result.sanitized_data or data

    # ── Tier 1: JSON cache (synchronous — fast) ───────────────────────────────
    cache = _get_cache()
    cached_result, cache_status, query_embedding = cache.lookup(
        data['case_type'], data['flight_type'], data['ticket_type'],
        data['payment_method'], data['accepted_alternative'], data['description'],
    )
    if cached_result:
        logger.info("Cache %s hit — returning immediately.", cache_status)
        return Response({"source": f"cache_{cache_status}", "result": cached_result})

    # ── Tier 2: PostgreSQL DB (synchronous — fast) ────────────────────────────
    db = _get_db()
    if db.enabled:
        db_result = db.get_by_hash(
            data['case_type'], data['flight_type'], data['ticket_type'],
            data['payment_method'], data['accepted_alternative'], data['description'],
        )
        if not db_result and query_embedding:
            db_result = db.get_by_semantic(query_embedding)
        if db_result:
            logger.info("DB hit — returning immediately.")
            cache.store(
                data['case_type'], data['flight_type'], data['ticket_type'],
                data['payment_method'], data['accepted_alternative'], data['description'],
                db_result, embedding=query_embedding,
            )
            return Response({"source": "database", "result": db_result})

    # ── Daily cost ceiling check ───────────────────────────────────────────────
    from .cost_guard import is_halted as cost_is_halted
    if cost_is_halted():
        return Response(
            {"error": "Service temporarily unavailable: daily cost ceiling reached. Try again tomorrow."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # ── Tier 3: Dispatch to Celery worker (async) ─────────────────────────────
    # .delay() puts the job in the Redis queue and returns IMMEDIATELY.
    # The Celery worker picks it up in the background.
    from .tasks import process_refund_case
    task = process_refund_case.delay(dict(data))

    logger.info("Dispatched task %s to Celery worker.", task.id)

    return Response(
        {"job_id": task.id, "status": "QUEUED"},
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(['GET'])
def job_status(request, job_id):
    """
    Poll the status of an async refund decision job.

    GET /api/v1/jobs/{job_id}/

    States:
      PENDING  → job is in the queue, not started yet
      STARTED  → a worker picked it up and is running the AI pipeline
      SUCCESS  → done! result is included in the response
      FAILURE  → something went wrong; error message included

    The frontend calls this every 2 seconds until it sees SUCCESS or FAILURE.
    """
    from celery.result import AsyncResult
    task = AsyncResult(job_id)

    if task.state == 'SUCCESS':
        return Response({
            'status': 'SUCCESS',
            'result': task.result,
        })
    elif task.state == 'FAILURE':
        return Response({
            'status': 'FAILURE',
            'error': str(task.result),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        # PENDING or STARTED
        return Response({'status': task.state})


class RefundDecisionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve past refund decisions.

    GET /api/v1/decisions/        → list all decisions (paginated)
    GET /api/v1/decisions/{id}/   → get a specific decision
    """
    queryset = RefundDecision.objects.all()

    def get_serializer_class(self):
        if self.action == 'list':
            return RefundDecisionListSerializer
        return RefundDecisionSerializer
