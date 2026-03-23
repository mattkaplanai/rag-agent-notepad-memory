"""
Contract tests: API response schema vs. what the frontend expects.

Each test documents a *contract* — a field the frontend reads and the type
it assumes. If a backend change breaks a contract the frontend breaks too,
even if unit tests still pass.

Contracts are derived from:
  frontend/src/api/client.js
  frontend/src/pages/HomePage.jsx
  frontend/src/pages/HistoryPage.jsx
  frontend/src/components/DecisionResult.jsx
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api_project.settings")

import django
django.setup()

import pytest
from unittest.mock import MagicMock, patch
from rest_framework.test import APIClient


# ── Shared fixtures / helpers ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def disable_ratelimit(monkeypatch):
    monkeypatch.setattr(
        "django_ratelimit.core.is_ratelimited",
        lambda *args, **kwargs: False,
    )


def api():
    return APIClient()


VALID_PAYLOAD = {
    "case_type": "Flight Cancellation",
    "flight_type": "Domestic (within US)",
    "ticket_type": "Non-refundable",
    "payment_method": "Credit Card",
    "accepted_alternative": "No — I did not accept any alternative",
    "description": "Delta cancelled my flight DL202 two days before departure. I did not accept rebooking.",
}

MOCK_RESULT = {
    "decision": "APPROVED",
    "confidence": "HIGH",
    "reasons": ["Airline cancelled — full refund required under DOT 14 CFR 259.5."],
    "applicable_regulations": ["14 CFR 259.5"],
    "refund_details": {"amount": "full ticket price", "timeline": "7 business days"},
    "decision_letter": "Dear Passenger, your refund has been approved.",
    "passenger_action_items": ["Submit refund request within 90 days."],
    "processing_time_seconds": 8.4,
    "source": "pipeline",
}


def _make_decision(**kwargs):
    from decisions.models import RefundDecision
    defaults = dict(
        case_type="Flight Cancellation",
        flight_type="Domestic (within US)",
        ticket_type="Non-refundable",
        payment_method="Credit Card",
        accepted_alternative="No — I did not accept any alternative",
        description="Delta cancelled my flight.",
        airline_name="Delta",
        flight_number="DL202",
        decision="APPROVED",
        confidence="HIGH",
        reasons=["Airline cancelled."],
        applicable_regulations=["14 CFR 259.5"],
        passenger_action_items=["Submit request."],
        processing_time_seconds=8.4,
    )
    defaults.update(kwargs)
    return RefundDecision.objects.create(**defaults)


# ── Contract: POST /api/v1/analyze/ — async path (202) ───────────────────────
#
# Frontend reads:  response.job_id  (string → passed to polling)
#                  response.status  (must equal "QUEUED")
# Source: HomePage.jsx line 113-116

@pytest.mark.django_db
class TestAnalyzeContractAsyncPath:

    @patch("decisions.views._get_cache")
    @patch("decisions.views._get_db")
    def _post(self, mock_db, mock_cache):
        mock_cache.return_value.lookup.return_value = (None, None, None)
        mock_db.return_value.enabled = False
        with patch("decisions.tasks.process_refund_case") as mock_task:
            mock_task.delay.return_value = MagicMock(id=str(uuid.uuid4()))
            return api().post("/api/v1/analyze/", VALID_PAYLOAD, format="json")

    def test_http_status_is_202(self):
        assert self._post().status_code == 202

    def test_job_id_present(self):
        """Frontend: if (response.job_id) → startPolling(response.job_id)"""
        r = self._post()
        assert "job_id" in r.data

    def test_job_id_is_string(self):
        """Frontend passes job_id directly to fetch(`/jobs/${jobId}/`)"""
        r = self._post()
        assert isinstance(r.data["job_id"], str)

    def test_job_id_is_non_empty(self):
        r = self._post()
        assert len(r.data["job_id"]) > 0

    def test_status_field_present(self):
        r = self._post()
        assert "status" in r.data

    def test_status_equals_queued(self):
        """Frontend sets jobStatus from response.status — expects 'QUEUED'"""
        r = self._post()
        assert r.data["status"] == "QUEUED"

    def test_no_result_field_on_async_path(self):
        """Frontend branches on presence of response.source to detect cache hit.
        Async path must NOT include result/source so the branch goes to polling."""
        r = self._post()
        assert "result" not in r.data
        assert "source" not in r.data


# ── Contract: POST /api/v1/analyze/ — cache hit path (200) ───────────────────
#
# Frontend reads:  response.source  (truthy string → skip polling)
#                  response.result  (object → passed to DecisionResult)
# Source: HomePage.jsx line 107-112

@pytest.mark.django_db
class TestAnalyzeContractCacheHitPath:

    @patch("decisions.views._get_cache")
    @patch("decisions.views._get_db")
    def _post(self, mock_db, mock_cache):
        mock_cache.return_value.lookup.return_value = (MOCK_RESULT, "exact", None)
        mock_db.return_value.enabled = False
        return api().post("/api/v1/analyze/", VALID_PAYLOAD, format="json")

    def test_http_status_is_200(self):
        assert self._post().status_code == 200

    def test_source_field_present(self):
        """Frontend: if (response.source && response.result) → cache hit branch"""
        r = self._post()
        assert "source" in r.data

    def test_source_is_truthy_string(self):
        r = self._post()
        assert isinstance(r.data["source"], str)
        assert len(r.data["source"]) > 0

    def test_source_starts_with_cache(self):
        """Frontend uses source as display label — backend always prefixes 'cache_'"""
        r = self._post()
        assert r.data["source"].startswith("cache_")

    def test_result_field_present(self):
        r = self._post()
        assert "result" in r.data

    def test_result_is_dict(self):
        """Frontend destructures result directly into DecisionResult component"""
        r = self._post()
        assert isinstance(r.data["result"], dict)

    def test_no_job_id_on_cache_path(self):
        """Frontend must not enter polling loop on cache hit"""
        r = self._post()
        assert "job_id" not in r.data


# ── Contract: POST /api/v1/analyze/ — error response ─────────────────────────
#
# Frontend reads:  error.detail  OR  error.description?.[0]
# Source: client.js line 27 — throw new Error(error.detail || error.description?.[0])

@pytest.mark.django_db
class TestAnalyzeContractErrorSchema:

    def test_validation_error_has_parseable_field(self):
        """Frontend catches error.detail or error.description[0] — at least one must exist."""
        r = api().post("/api/v1/analyze/", {}, format="json")
        assert r.status_code == 400
        data = r.data
        has_detail = "detail" in data
        has_field_errors = any(isinstance(v, list) for v in data.values())
        assert has_detail or has_field_errors, (
            "Frontend needs error.detail or a field with list of messages"
        )

    def test_invalid_case_type_error_has_case_type_key(self):
        """DRF serializer returns {field: [messages]} — frontend reads description[0]"""
        r = api().post("/api/v1/analyze/", {**VALID_PAYLOAD, "case_type": "Bad"}, format="json")
        assert r.status_code == 400
        assert "case_type" in r.data

    def test_short_description_error_has_description_key(self):
        r = api().post("/api/v1/analyze/", {**VALID_PAYLOAD, "description": "x"}, format="json")
        assert r.status_code == 400
        assert "description" in r.data

    def test_field_error_values_are_lists(self):
        """Frontend reads error.description?.[0] — must be indexable list"""
        r = api().post("/api/v1/analyze/", {**VALID_PAYLOAD, "description": "x"}, format="json")
        assert isinstance(r.data["description"], list)
        assert len(r.data["description"]) > 0

    def test_field_error_messages_are_strings(self):
        r = api().post("/api/v1/analyze/", {**VALID_PAYLOAD, "description": "x"}, format="json")
        assert isinstance(r.data["description"][0], str)


# ── Contract: GET /api/v1/jobs/{id}/ — job status polling ────────────────────
#
# Frontend reads:  data.status   ("PENDING"|"STARTED"|"SUCCESS"|"FAILURE")
#                  data.result   (object, only when SUCCESS)
#                  data.error    (string, only when FAILURE)
# Source: HomePage.jsx lines 74-88

@pytest.mark.django_db
class TestJobStatusContract:

    @patch("celery.result.AsyncResult")
    def test_success_has_status_field(self, mock_ar):
        mock_ar.return_value.state = "SUCCESS"
        mock_ar.return_value.result = MOCK_RESULT
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert "status" in r.data

    @patch("celery.result.AsyncResult")
    def test_success_status_value(self, mock_ar):
        """Frontend checks data.status === 'SUCCESS' to stop polling"""
        mock_ar.return_value.state = "SUCCESS"
        mock_ar.return_value.result = MOCK_RESULT
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert r.data["status"] == "SUCCESS"

    @patch("celery.result.AsyncResult")
    def test_success_has_result_field(self, mock_ar):
        """Frontend: setResult(data.result) — must be present on SUCCESS"""
        mock_ar.return_value.state = "SUCCESS"
        mock_ar.return_value.result = MOCK_RESULT
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert "result" in r.data

    @patch("celery.result.AsyncResult")
    def test_success_result_is_dict(self, mock_ar):
        mock_ar.return_value.state = "SUCCESS"
        mock_ar.return_value.result = MOCK_RESULT
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert isinstance(r.data["result"], dict)

    @patch("celery.result.AsyncResult")
    def test_failure_has_status_field(self, mock_ar):
        mock_ar.return_value.state = "FAILURE"
        mock_ar.return_value.result = RuntimeError("Pipeline crashed")
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert "status" in r.data

    @patch("celery.result.AsyncResult")
    def test_failure_status_value(self, mock_ar):
        """Frontend checks data.status === 'FAILURE' to show error message"""
        mock_ar.return_value.state = "FAILURE"
        mock_ar.return_value.result = RuntimeError("Pipeline crashed")
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert r.data["status"] == "FAILURE"

    @patch("celery.result.AsyncResult")
    def test_failure_has_error_field(self, mock_ar):
        """Frontend: setError(data.error || fallback) — must be present on FAILURE"""
        mock_ar.return_value.state = "FAILURE"
        mock_ar.return_value.result = RuntimeError("Pipeline crashed")
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert "error" in r.data

    @patch("celery.result.AsyncResult")
    def test_failure_error_is_string(self, mock_ar):
        """Frontend passes error directly to setError() as a string"""
        mock_ar.return_value.state = "FAILURE"
        mock_ar.return_value.result = RuntimeError("Pipeline crashed")
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert isinstance(r.data["error"], str)

    @patch("celery.result.AsyncResult")
    def test_pending_has_status_field(self, mock_ar):
        mock_ar.return_value.state = "PENDING"
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert r.data["status"] == "PENDING"

    @patch("celery.result.AsyncResult")
    def test_started_has_status_field(self, mock_ar):
        mock_ar.return_value.state = "STARTED"
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert r.data["status"] == "STARTED"

    @patch("celery.result.AsyncResult")
    def test_pending_has_no_result_field(self, mock_ar):
        """Frontend only reads data.result on SUCCESS — other states must not include it"""
        mock_ar.return_value.state = "PENDING"
        r = api().get(f"/api/v1/jobs/{uuid.uuid4()}/")
        assert "result" not in r.data


# ── Contract: GET /api/v1/decisions/ — history list ──────────────────────────
#
# Frontend reads:  data.count      (number → Math.ceil for pagination)
#                  data.next       (string|null → show next button)
#                  data.previous   (string|null → show prev button)
#                  data.results[]  (array → map over rows)
# Each row:  d.id, d.case_type, d.flight_type, d.airline_name,
#            d.decision, d.confidence, d.processing_time_seconds, d.created_at
# Source: HistoryPage.jsx lines 26-34, 83-104

@pytest.mark.django_db
class TestDecisionsListContract:

    def test_response_has_count(self):
        """Frontend: Math.ceil(data.count / 20) for total pages"""
        r = api().get("/api/v1/decisions/")
        assert "count" in r.data

    def test_count_is_integer(self):
        r = api().get("/api/v1/decisions/")
        assert isinstance(r.data["count"], int)

    def test_response_has_next(self):
        """Frontend checks data.next to show/hide next-page button"""
        r = api().get("/api/v1/decisions/")
        assert "next" in r.data

    def test_response_has_previous(self):
        r = api().get("/api/v1/decisions/")
        assert "previous" in r.data

    def test_response_has_results(self):
        """Frontend: data.results.map(d => ...) — must be a list"""
        r = api().get("/api/v1/decisions/")
        assert "results" in r.data
        assert isinstance(r.data["results"], list)

    def test_result_item_has_id(self):
        """Frontend: key={d.id}"""
        _make_decision()
        r = api().get("/api/v1/decisions/")
        item = r.data["results"][0]
        assert "id" in item
        assert isinstance(item["id"], int)

    def test_result_item_has_case_type(self):
        _make_decision()
        item = api().get("/api/v1/decisions/").data["results"][0]
        assert "case_type" in item
        assert isinstance(item["case_type"], str)

    def test_result_item_has_flight_type(self):
        _make_decision()
        item = api().get("/api/v1/decisions/").data["results"][0]
        assert "flight_type" in item
        assert isinstance(item["flight_type"], str)

    def test_result_item_has_airline_name(self):
        """Frontend: d.airline_name || <span>—</span> — field must exist (can be empty)"""
        _make_decision()
        item = api().get("/api/v1/decisions/").data["results"][0]
        assert "airline_name" in item

    def test_result_item_has_decision(self):
        """Frontend passes d.decision to <DecisionBadge> — must be present"""
        _make_decision()
        item = api().get("/api/v1/decisions/").data["results"][0]
        assert "decision" in item
        assert item["decision"] in {"APPROVED", "DENIED", "PARTIAL", "ERROR"}

    def test_result_item_has_confidence(self):
        _make_decision()
        item = api().get("/api/v1/decisions/").data["results"][0]
        assert "confidence" in item
        assert item["confidence"] in {"HIGH", "MEDIUM", "LOW"}

    def test_result_item_has_processing_time_seconds(self):
        """Frontend: d.processing_time_seconds ?? '—' — field must exist (can be null)"""
        _make_decision()
        item = api().get("/api/v1/decisions/").data["results"][0]
        assert "processing_time_seconds" in item

    def test_result_item_has_created_at(self):
        """Frontend: new Date(d.created_at).toLocaleDateString() — must be ISO string"""
        _make_decision()
        item = api().get("/api/v1/decisions/").data["results"][0]
        assert "created_at" in item
        assert isinstance(item["created_at"], str)
        # Must be parseable as a date
        from datetime import datetime
        datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))

    def test_list_does_not_expose_reasons(self):
        """Frontend only uses compact fields in list — heavy fields must be absent
        (prevents accidentally breaking pagination performance)"""
        _make_decision()
        item = api().get("/api/v1/decisions/").data["results"][0]
        assert "reasons" not in item
        assert "analysis_steps" not in item
        assert "decision_letter" not in item


# ── Contract: Decision result object ─────────────────────────────────────────
#
# This is the object the frontend receives EITHER from:
#   • POST /analyze/ cache hit:  response.result
#   • GET  /jobs/{id}/ SUCCESS:  data.result
# Frontend destructures it in DecisionResult.jsx line 30-46.

@pytest.mark.django_db
class TestDecisionResultObjectContract:
    """Verify the shape of the result object passed to DecisionResult.jsx."""

    def _get_result(self):
        """Get result via cache hit path — same object shape as job SUCCESS."""
        with patch("decisions.views._get_cache") as mock_cache, \
             patch("decisions.views._get_db") as mock_db:
            mock_cache.return_value.lookup.return_value = (MOCK_RESULT, "exact", None)
            mock_db.return_value.enabled = False
            r = api().post("/api/v1/analyze/", VALID_PAYLOAD, format="json")
        return r.data["result"]

    def test_has_decision(self):
        """Frontend: const { decision, ... } = data"""
        assert "decision" in self._get_result()

    def test_decision_is_uppercase_enum(self):
        """DecisionBadge component expects uppercase: APPROVED|DENIED|PARTIAL|ERROR"""
        result = self._get_result()
        assert result["decision"] in {"APPROVED", "DENIED", "PARTIAL", "ERROR"}

    def test_has_confidence(self):
        assert "confidence" in self._get_result()

    def test_confidence_is_uppercase_enum(self):
        assert self._get_result()["confidence"] in {"HIGH", "MEDIUM", "LOW"}

    def test_has_reasons(self):
        """Frontend: const { reasons = [], ... } = data — defaults to [] if missing"""
        assert "reasons" in self._get_result()

    def test_reasons_is_list(self):
        """Frontend: reasons.length > 0 to decide whether to render section"""
        assert isinstance(self._get_result()["reasons"], list)

    def test_has_applicable_regulations(self):
        """Frontend: applicable_regulations = [] default — must be list or absent"""
        result = self._get_result()
        if "applicable_regulations" in result:
            assert isinstance(result["applicable_regulations"], list)

    def test_has_passenger_action_items(self):
        result = self._get_result()
        if "passenger_action_items" in result:
            assert isinstance(result["passenger_action_items"], list)

    def test_decision_letter_is_string_or_absent(self):
        """Frontend: if (decision_letter) → render letter block"""
        result = self._get_result()
        if "decision_letter" in result and result["decision_letter"] is not None:
            assert isinstance(result["decision_letter"], str)

    def test_processing_time_seconds_is_number_or_absent(self):
        """Frontend displays processing_time_seconds as a number"""
        result = self._get_result()
        if "processing_time_seconds" in result and result["processing_time_seconds"] is not None:
            assert isinstance(result["processing_time_seconds"], (int, float))


# ── Contract: GET /api/v1/health/ ────────────────────────────────────────────
#
# Frontend reads:  data.status         (=== 'healthy' for green dot)
#                  data.total_decisions (displayed as count)
# Source: HomePage.jsx lines 38-42, 142-145

@pytest.mark.django_db
class TestHealthContract:

    def test_has_status(self):
        """Frontend: health.status === 'healthy' → green dot"""
        r = api().get("/api/v1/health/")
        assert "status" in r.data

    def test_status_is_string(self):
        assert isinstance(api().get("/api/v1/health/").data["status"], str)

    def test_status_value_is_healthy(self):
        """Frontend renders '● API healthy' — value must be exactly 'healthy'"""
        assert api().get("/api/v1/health/").data["status"] == "healthy"

    def test_has_total_decisions(self):
        """Frontend: '{health.total_decisions} decisions processed'"""
        r = api().get("/api/v1/health/")
        assert "total_decisions" in r.data

    def test_total_decisions_is_integer(self):
        """Frontend uses this as a display number — must be int, not string"""
        assert isinstance(api().get("/api/v1/health/").data["total_decisions"], int)

    def test_total_decisions_reflects_db(self):
        _make_decision()
        _make_decision()
        assert api().get("/api/v1/health/").data["total_decisions"] == 2
