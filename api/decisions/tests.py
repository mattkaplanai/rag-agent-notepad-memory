"""Tests for the refund decision API."""

from django.test import TestCase
from rest_framework.test import APIClient

from .models import RefundDecision


class HealthCheckTest(TestCase):
    """Test the /api/v1/health/ endpoint."""

    def setUp(self):
        self.client = APIClient()

    def test_health_check_returns_200(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)

    def test_health_check_contains_status(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.data["status"], "healthy")

    def test_health_check_contains_decision_count(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.data["total_decisions"], 0)

    def test_health_check_counts_decisions(self):
        RefundDecision.objects.create(
            case_type="Flight Cancellation",
            flight_type="Domestic (within US)",
            ticket_type="Non-refundable",
            payment_method="Credit Card",
            accepted_alternative="No",
            description="Test",
            decision="APPROVED",
            confidence="HIGH",
        )
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.data["total_decisions"], 1)


class AnalyzeCaseValidationTest(TestCase):
    """Test input validation for /api/v1/analyze/."""

    def setUp(self):
        self.client = APIClient()

    def test_missing_fields_returns_400(self):
        response = self.client.post("/api/v1/analyze/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_invalid_case_type_returns_400(self):
        response = self.client.post("/api/v1/analyze/", {
            "case_type": "Invalid Type",
            "flight_type": "Domestic (within US)",
            "ticket_type": "Non-refundable",
            "payment_method": "Credit Card",
            "accepted_alternative": "No — I did not accept any alternative",
            "description": "My flight was cancelled and I need a refund.",
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_short_description_returns_400(self):
        response = self.client.post("/api/v1/analyze/", {
            "case_type": "Flight Cancellation",
            "flight_type": "Domestic (within US)",
            "ticket_type": "Non-refundable",
            "payment_method": "Credit Card",
            "accepted_alternative": "No — I did not accept any alternative",
            "description": "short",
        }, format="json")
        self.assertEqual(response.status_code, 400)


class RefundDecisionModelTest(TestCase):
    """Test the RefundDecision model."""

    def test_create_decision(self):
        decision = RefundDecision.objects.create(
            case_type="Flight Cancellation",
            flight_type="Domestic (within US)",
            ticket_type="Non-refundable",
            payment_method="Credit Card",
            accepted_alternative="No",
            description="Flight was cancelled.",
            decision="APPROVED",
            confidence="HIGH",
            analysis_steps=["Step 1"],
            reasons=["Reason 1"],
        )
        self.assertEqual(decision.decision, "APPROVED")
        self.assertEqual(decision.confidence, "HIGH")

    def test_str_representation(self):
        decision = RefundDecision.objects.create(
            case_type="Baggage Lost or Delayed",
            flight_type="International",
            ticket_type="Refundable",
            payment_method="Debit Card",
            accepted_alternative="No",
            description="Bag was lost.",
            decision="DENIED",
            confidence="MEDIUM",
            airline_name="Delta",
        )
        self.assertIn("DENIED", str(decision))
        self.assertIn("Delta", str(decision))

    def test_ordering_by_created_at(self):
        d1 = RefundDecision.objects.create(
            case_type="Flight Cancellation", flight_type="Domestic (within US)",
            ticket_type="Non-refundable", payment_method="Credit Card",
            accepted_alternative="No", description="First case.",
            decision="APPROVED", confidence="HIGH",
        )
        d2 = RefundDecision.objects.create(
            case_type="Flight Cancellation", flight_type="International",
            ticket_type="Refundable", payment_method="Cash",
            accepted_alternative="No", description="Second case.",
            decision="DENIED", confidence="LOW",
        )
        decisions = list(RefundDecision.objects.all())
        self.assertEqual(decisions[0].id, d2.id)

    def test_json_fields_default(self):
        decision = RefundDecision.objects.create(
            case_type="Flight Cancellation", flight_type="Domestic (within US)",
            ticket_type="Non-refundable", payment_method="Credit Card",
            accepted_alternative="No", description="Test.",
            decision="APPROVED", confidence="HIGH",
        )
        self.assertEqual(decision.analysis_steps, [])
        self.assertEqual(decision.reasons, [])
        self.assertIsNone(decision.refund_details)


class RefundDecisionViewSetTest(TestCase):
    """Test the decisions list/detail endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.decision = RefundDecision.objects.create(
            case_type="Flight Cancellation",
            flight_type="Domestic (within US)",
            ticket_type="Non-refundable",
            payment_method="Credit Card",
            accepted_alternative="No",
            description="Flight cancelled, need refund.",
            decision="APPROVED",
            confidence="HIGH",
            analysis_steps=["Checked delay threshold"],
            reasons=["Flight was cancelled by airline"],
            applicable_regulations=["14 CFR 259"],
            processing_time_seconds=12.5,
        )

    def test_list_decisions(self):
        response = self.client.get("/api/v1/decisions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_retrieve_decision(self):
        response = self.client.get(f"/api/v1/decisions/{self.decision.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["decision"], "APPROVED")
        self.assertEqual(response.data["case_type"], "Flight Cancellation")

    def test_list_returns_compact_fields(self):
        response = self.client.get("/api/v1/decisions/")
        result = response.data["results"][0]
        self.assertIn("id", result)
        self.assertIn("decision", result)
        self.assertNotIn("analysis_steps", result)

    def test_detail_returns_all_fields(self):
        response = self.client.get(f"/api/v1/decisions/{self.decision.id}/")
        self.assertIn("analysis_steps", response.data)
        self.assertIn("reasons", response.data)
        self.assertIn("applicable_regulations", response.data)

    def test_404_for_missing_decision(self):
        response = self.client.get("/api/v1/decisions/9999/")
        self.assertEqual(response.status_code, 404)
