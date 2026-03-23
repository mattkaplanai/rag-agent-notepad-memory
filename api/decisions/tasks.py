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

# Module-level cache — agents are built once per worker process, then reused.
# _loaded_index_version tracks which index version the pipeline was built from.
# When active_version.txt changes, _get_pipeline() detects it and rebuilds.
_pipeline = None
_loaded_index_version = None  # int or None


def _get_pipeline():
    """
    Lazy-load the multi-agent pipeline once per worker process.
    Automatically reloads if the active index version has changed (new ingestion run).
    """
    global _pipeline, _loaded_index_version

    # Check whether the index was swapped since we last loaded
    try:
        from app.rag.versioned_indexer import get_active_version
        current_version = get_active_version()
    except Exception:
        current_version = None

    if _pipeline is not None and _loaded_index_version == current_version:
        return _pipeline  # hot path — version unchanged, reuse in-memory pipeline

    from app.agents.researcher import build_researcher_parallel
    from app.agents.analyst import build_analyst
    from app.agents.writer import build_writer

    logger.info("[Celery worker] (Re)building pipeline (index v%s)...", current_version)

    try:
        from app.rag.versioned_indexer import load_active_index
        index = load_active_index()
    except Exception:
        from app.rag.indexer import build_or_load_index
        index = build_or_load_index()

    _pipeline = {
        'index': index,
        'researcher': build_researcher_parallel(index),
        'analyst': build_analyst(),
        'writer': build_writer(),
    }
    _loaded_index_version = current_version
    logger.info("[Celery worker] Pipeline ready (index v%s).", current_version)
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

    tenant_slug = case_data.get('tenant_id', '')

    # ── Tier 1: JSON cache ────────────────────────────────────────────────────
    from app.cache.decision_cache import DecisionCache
    cache = DecisionCache()
    cached_result, cache_status, query_embedding = cache.lookup(
        case_data['case_type'], case_data['flight_type'], case_data['ticket_type'],
        case_data['payment_method'], case_data['accepted_alternative'], case_data['description'],
        tenant_id=tenant_slug,
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
            tenant_id=tenant_slug,
        )
        if not db_result and query_embedding:
            db_result = db.get_by_semantic(query_embedding, tenant_id=tenant_slug)
        if db_result:
            logger.info("[Task %s] DB hit.", self.request.id)
            cache.store(
                case_data['case_type'], case_data['flight_type'], case_data['ticket_type'],
                case_data['payment_method'], case_data['accepted_alternative'], case_data['description'],
                db_result, embedding=query_embedding, tenant_id=tenant_slug,
            )
            return {'source': 'database', 'result': db_result}

    # ── Tier 3: Full multi-agent pipeline ─────────────────────────────────────
    from app.agents.classifier import run_classifier, build_case_summary
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
            final, embedding=query_embedding, tenant_id=tenant_slug,
        )
        db.insert(
            case_data['case_type'], case_data['flight_type'], case_data['ticket_type'],
            case_data['payment_method'], case_data['accepted_alternative'], case_data['description'],
            final, embedding=query_embedding, tenant_id=tenant_slug,
        )

    # Save to Django DB
    from decisions.models import RefundDecision, Tenant, IndexVersion
    tenant = None
    if tenant_slug:
        tenant = Tenant.objects.filter(slug=tenant_slug, is_active=True).first()

    # Stamp the decision with the index version that served it
    index_version_obj = None
    try:
        from app.rag.versioned_indexer import get_active_version
        av = get_active_version()
        if av is not None:
            index_version_obj = IndexVersion.objects.filter(version=av, status='active').first()
    except Exception:
        pass

    record = RefundDecision.objects.create(
        tenant=tenant,
        index_version=index_version_obj,
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


# ── Scheduled ingestion task ───────────────────────────────────────────────────

@shared_task(name='decisions.refresh_index')
def refresh_index() -> dict:
    """
    Scheduled ingestion pipeline — triggered by Celery Beat (daily at 02:00 UTC).

    Steps:
    1. Scan data/bilgiler/ and compute a manifest (filename + size + sha256 prefix).
    2. Compare with the last active version's manifest — skip if nothing changed.
    3. Build a new versioned index into storage/v{N}/ + storage/chroma_v{N}/.
    4. Atomically activate: write storage/active_version.txt → N.
    5. Record the version in Django DB for full audit trail.

    Any worker that calls _get_pipeline() after step 4 will automatically reload
    the new index on its next task.
    """
    from django.db.models import Max
    from django.utils import timezone
    from decisions.models import IndexVersion
    from app.rag.versioned_indexer import (
        get_doc_manifest,
        get_active_version,
        build_versioned_index,
        activate_version,
    )

    logger.info("[refresh_index] Scanning data/bilgiler/ for changes...")
    new_manifest = get_doc_manifest()

    # Compare with the active version's manifest — skip rebuild if identical
    active_v = get_active_version()
    if active_v is not None:
        try:
            last = IndexVersion.objects.get(version=active_v, status='active')
            if last.doc_manifest == new_manifest:
                logger.info("[refresh_index] No changes detected — skipping rebuild.")
                return {'status': 'skipped', 'reason': 'no_changes', 'active_version': active_v}
        except IndexVersion.DoesNotExist:
            pass  # DB record missing — rebuild anyway

    # Determine next sequential version number
    last_version = IndexVersion.objects.aggregate(m=Max('version'))['m'] or 0
    next_version = last_version + 1

    logger.info("[refresh_index] Starting build for v%d...", next_version)

    # Create DB record immediately so failures are also recorded
    record = IndexVersion.objects.create(
        version=next_version,
        status='building',
        doc_manifest=new_manifest,
        notes=f"Scheduled ingestion run at {timezone.now().isoformat()}",
    )

    try:
        doc_count, _ = build_versioned_index(next_version)
        activate_version(next_version)

        record.status = 'active'
        record.doc_count = doc_count
        record.activated_at = timezone.now()
        record.save()

        # Archive the previous active version
        if active_v is not None:
            IndexVersion.objects.filter(version=active_v, status='active').update(status='archived')

        # Invalidate this worker's pipeline cache so it picks up the new index
        global _loaded_index_version
        _loaded_index_version = None

        logger.info("[refresh_index] Done. Active → v%d (%d docs).", next_version, doc_count)
        return {'status': 'built', 'version': next_version, 'doc_count': doc_count}

    except Exception as exc:
        record.status = 'failed'
        record.notes += f"\nFailed: {exc}"
        record.save()
        logger.error("[refresh_index] Build failed for v%d: %s", next_version, exc)
        raise
