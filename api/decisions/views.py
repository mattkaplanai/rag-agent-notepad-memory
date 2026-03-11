"""API views for the refund decision system."""

import logging
import time

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


def _get_pipeline():
    """Lazy-load the multi-agent pipeline (expensive, only init once)."""
    if not hasattr(_get_pipeline, '_agents'):
        from app.rag.indexer import build_or_load_index
        from app.agents.researcher import build_researcher
        from app.agents.analyst import build_analyst
        from app.agents.writer import build_writer

        logger.info("Building document index and agents...")
        index = build_or_load_index()
        _get_pipeline._agents = {
            'index': index,
            'researcher': build_researcher(index),
            'analyst': build_analyst(),
            'writer': build_writer(),
        }
        logger.info("Pipeline ready.")
    return _get_pipeline._agents


@api_view(['GET'])
def health_check(request):
    """Health check endpoint."""
    return Response({
        "status": "healthy",
        "service": "Airlines Refund Decision API",
        "total_decisions": RefundDecision.objects.count(),
    })


@api_view(['POST'])
def analyze_case(request):
    """
    Submit a refund case for analysis.

    POST /api/v1/analyze/
    Body: {case_type, flight_type, ticket_type, payment_method, accepted_alternative, description}
    Returns: full decision with analysis, reasons, regulations, refund details
    """
    serializer = RefundRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    start_time = time.time()

    from app.agents.classifier import run_classifier, build_case_summary
    from app.agents.judge import run_judge
    from app.agents.supervisor import run_multi_agent

    agents = _get_pipeline()

    classifier_output = run_classifier(
        data['case_type'], data['flight_type'], data['ticket_type'],
        data['payment_method'], data['accepted_alternative'], data['description'],
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

    processing_time = round(time.time() - start_time, 2)

    record = RefundDecision.objects.create(
        case_type=data['case_type'],
        flight_type=data['flight_type'],
        ticket_type=data['ticket_type'],
        payment_method=data['payment_method'],
        accepted_alternative=data['accepted_alternative'],
        description=data['description'],
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

    return Response(
        RefundDecisionSerializer(record).data,
        status=status.HTTP_201_CREATED,
    )


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
