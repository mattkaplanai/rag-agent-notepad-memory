"""
Celery task for the refund decision pipeline.

WHY A SEPARATE FILE?
  Celery autodiscover_tasks() scans every app for a tasks.py file.
  Putting tasks here keeps them separate from views (HTTP handling) and
  models (database schema).

HOW @shared_task WORKS:
  @shared_task means this function can be imported anywhere without
  creating a circular import. Celery replaces it with the full Task
  class at runtime.

WORKER INITIALIZATION:
  Each Celery worker process initializes the RAG index and agents once
  when the first task runs (lazy loading via _get_pipeline()).
  After that, all tasks in that worker reuse the same loaded agents —
  exactly like how the Django view worked before.
"""

import logging
import time

from celery import shared_task

logger = logging.getLogger(__name__)

# Module-level cache — agents are built once per worker process, then reused
_pipeline = None


def _get_pipeline():
    """Lazy-load the multi-agent pipeline once per worker process."""
    global _pipeline
    if _pipeline is None:
        from app.rag.indexer import build_or_load_index
        from app.agents.researcher import build_researcher_parallel
        from app.agents.analyst import build_analyst
        from app.agents.writer import build_writer

        logger.info("[Celery worker] Building index and agents...")
        index = build_or_load_index()
        _pipeline = {
            'index': index,
            'researcher': build_researcher_parallel(index),
            'analyst': build_analyst(),
            'writer': build_writer(),
        }
        logger.info("[Celery worker] Pipeline ready.")
    return _pipeline


@shared_task(bind=True, name='decisions.process_refund_case')
def process_refund_case(self, case_data: dict) -> dict:
    """
    Run the full AI refund decision pipeline asynchronously.

    This task is dispatched by the Django view and runs in a Celery worker.
    The Django view returns immediately with a job_id; this task runs
    in the background and stores its result in Redis.

    Args:
        case_data: dict with keys matching RefundRequest fields
                   (already validated + input-guarded by the view)

    Returns:
        dict with the full decision result
    """
    start_time = time.time()
    logger.info("[Task %s] Starting pipeline for case_type=%s", self.request.id, case_data.get('case_type'))

    # ── Tier 1: JSON cache ────────────────────────────────────────────────────
    from app.cache.decision_cache import DecisionCache
    cache = DecisionCache()
    cached_result, cache_status, query_embedding = cache.lookup(
        case_data['case_type'], case_data['flight_type'], case_data['ticket_type'],
        case_data['payment_method'], case_data['accepted_alternative'], case_data['description'],
    )
    if cached_result:
        logger.info("[Task %s] Cache %s hit.", self.request.id, cache_status)
        return {'source': f'cache_{cache_status}', 'result': cached_result}

    # ── Tier 2: PostgreSQL DB ─────────────────────────────────────────────────
    from app.db.decision_db import DecisionDB
    db = DecisionDB()
    if db.enabled:
        db_result = db.get_by_hash(
            case_data['case_type'], case_data['flight_type'], case_data['ticket_type'],
            case_data['payment_method'], case_data['accepted_alternative'], case_data['description'],
        )
        if not db_result and query_embedding:
            db_result = db.get_by_semantic(query_embedding)
        if db_result:
            logger.info("[Task %s] DB hit.", self.request.id)
            cache.store(
                case_data['case_type'], case_data['flight_type'], case_data['ticket_type'],
                case_data['payment_method'], case_data['accepted_alternative'], case_data['description'],
                db_result, embedding=query_embedding,
            )
            return {'source': 'database', 'result': db_result}

    # ── Tier 3: Full multi-agent pipeline ─────────────────────────────────────
    from app.agents.classifier import run_classifier, build_case_summary
    from app.agents.researcher import run_researcher_parallel
    from app.agents.judge import run_judge
    from app.agents.supervisor import run_multi_agent

    agents = _get_pipeline()

    classifier_output = run_classifier(
        case_data['case_type'], case_data['flight_type'], case_data['ticket_type'],
        case_data['payment_method'], case_data['accepted_alternative'], case_data['description'],
    )
    case_summary = build_case_summary(classifier_output)

    ma_result = run_multi_agent(
        agents['researcher'], agents['analyst'], agents['writer'], case_summary,
    )

    judge_verdict = run_judge(classifier_output, ma_result.supervisor_decision)
    final = ma_result.supervisor_decision

    if not judge_verdict.approved and judge_verdict.override_decision:
        final = final.copy()
        final['decision'] = judge_verdict.override_decision
        if judge_verdict.override_reasons:
            final['reasons'] = judge_verdict.override_reasons
        final['judge_override'] = True
        final['judge_explanation'] = judge_verdict.explanation

    # Output guard
    from app.guards import run_output_guard
    output_result = run_output_guard(final)
    if not output_result.passed:
        logger.warning("[Task %s] Output guard blocked: %s", self.request.id, output_result.block_reason)
        final = output_result.override_decision or final

    processing_time = round(time.time() - start_time, 2)

    # Store in cache + DB for future lookups
    if final.get('decision') != 'ERROR':
        cache.store(
            case_data['case_type'], case_data['flight_type'], case_data['ticket_type'],
            case_data['payment_method'], case_data['accepted_alternative'], case_data['description'],
            final, embedding=query_embedding,
        )
        db.insert(
            case_data['case_type'], case_data['flight_type'], case_data['ticket_type'],
            case_data['payment_method'], case_data['accepted_alternative'], case_data['description'],
            final, embedding=query_embedding,
        )

    # Save to Django DB
    # (Django is already configured by Celery's DjangoLoader at worker startup)
    from decisions.models import RefundDecision
    record = RefundDecision.objects.create(
        case_type=case_data['case_type'],
        flight_type=case_data['flight_type'],
        ticket_type=case_data['ticket_type'],
        payment_method=case_data['payment_method'],
        accepted_alternative=case_data['accepted_alternative'],
        description=case_data['description'],
        airline_name=classifier_output.airline_name or '',
        flight_number=classifier_output.flight_number or '',
        flight_date=classifier_output.flight_date or '',
        flight_duration_hours=classifier_output.flight_duration_hours,
        delay_hours=classifier_output.delay_hours,
        bag_delay_hours=classifier_output.bag_delay_hours,
        ticket_price=classifier_output.ticket_price,
        decision=final.get('decision', 'ERROR'),
        confidence=final.get('confidence', 'LOW'),
        analysis_steps=final.get('analysis_steps', []),
        reasons=final.get('reasons', []),
        applicable_regulations=final.get('applicable_regulations', []),
        refund_details=final.get('refund_details'),
        passenger_action_items=final.get('passenger_action_items', []),
        tools_used=final.get('tools_used', []),
        decision_letter=final.get('decision_letter') or '',
        raw_result=final,
        processing_time_seconds=processing_time,
    )

    logger.info("[Task %s] Done in %.1fs → %s", self.request.id, processing_time, final.get('decision'))

    # Return the full serialized result for the frontend to consume
    from decisions.serializers import RefundDecisionSerializer
    return RefundDecisionSerializer(record).data
