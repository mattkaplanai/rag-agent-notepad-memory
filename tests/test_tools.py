"""Tests for refund decision tools — delay, baggage, calculator, timeline."""

import json
from datetime import date, timedelta

import pytest

from app.tools.check_delay import check_delay_threshold
from app.tools.check_baggage import check_baggage_threshold
from app.tools.refund_calculator import calculate_refund
from app.tools.timeline_calculator import calculate_refund_timeline


# ── Helpers ──────────────────────────────────────────────────────────────────

def parse(tool_output: str) -> dict:
    """All tools return JSON strings — parse them."""
    return json.loads(tool_output)


# ── check_delay_threshold ─────────────────────────────────────────────────────

class TestCheckDelayThreshold:
    """DOT rules: domestic >= 3h significant, international >= 6h significant."""

    # Domestic
    def test_domestic_exactly_at_threshold_is_significant(self):
        result = parse(check_delay_threshold.invoke({"flight_type": "Domestic (within US)", "delay_hours": 3.0}))
        assert result["is_significant_delay"] is True

    def test_domestic_just_below_threshold_not_significant(self):
        result = parse(check_delay_threshold.invoke({"flight_type": "Domestic (within US)", "delay_hours": 2.9}))
        assert result["is_significant_delay"] is False

    def test_domestic_well_above_threshold(self):
        result = parse(check_delay_threshold.invoke({"flight_type": "Domestic (within US)", "delay_hours": 5.0}))
        assert result["is_significant_delay"] is True

    def test_domestic_threshold_value_correct(self):
        result = parse(check_delay_threshold.invoke({"flight_type": "Domestic (within US)", "delay_hours": 1.0}))
        assert result["threshold_hours"] == 3.0

    # International
    def test_international_exactly_at_threshold_is_significant(self):
        result = parse(check_delay_threshold.invoke({"flight_type": "International", "delay_hours": 6.0}))
        assert result["is_significant_delay"] is True

    def test_international_just_below_threshold_not_significant(self):
        result = parse(check_delay_threshold.invoke({"flight_type": "International", "delay_hours": 5.9}))
        assert result["is_significant_delay"] is False

    def test_international_threshold_value_correct(self):
        result = parse(check_delay_threshold.invoke({"flight_type": "International", "delay_hours": 1.0}))
        assert result["threshold_hours"] == 6.0

    # Case insensitivity
    def test_flight_type_case_insensitive(self):
        r1 = parse(check_delay_threshold.invoke({"flight_type": "domestic (within us)", "delay_hours": 3.0}))
        r2 = parse(check_delay_threshold.invoke({"flight_type": "DOMESTIC (WITHIN US)", "delay_hours": 3.0}))
        assert r1["is_significant_delay"] == r2["is_significant_delay"]

    # Return shape
    def test_returns_required_fields(self):
        result = parse(check_delay_threshold.invoke({"flight_type": "Domestic (within US)", "delay_hours": 4.0}))
        assert all(k in result for k in ["is_significant_delay", "threshold_hours", "actual_delay_hours", "rule"])

    def test_actual_delay_hours_matches_input(self):
        result = parse(check_delay_threshold.invoke({"flight_type": "International", "delay_hours": 7.5}))
        assert result["actual_delay_hours"] == 7.5


# ── check_baggage_threshold ───────────────────────────────────────────────────

class TestCheckBaggageThreshold:
    """DOT rules: domestic > 12h, intl ≤12h flight > 15h, intl >12h flight > 30h."""

    # Domestic (threshold > 12h, exclusive)
    def test_domestic_at_threshold_not_significant(self):
        result = parse(check_baggage_threshold.invoke({
            "flight_type": "Domestic (within US)", "flight_duration_hours": 3.0, "bag_delay_hours": 12.0
        }))
        assert result["is_significantly_delayed"] is False  # > not >=

    def test_domestic_just_above_threshold_significant(self):
        result = parse(check_baggage_threshold.invoke({
            "flight_type": "Domestic (within US)", "flight_duration_hours": 3.0, "bag_delay_hours": 12.1
        }))
        assert result["is_significantly_delayed"] is True

    def test_domestic_threshold_value_correct(self):
        result = parse(check_baggage_threshold.invoke({
            "flight_type": "Domestic (within US)", "flight_duration_hours": 3.0, "bag_delay_hours": 5.0
        }))
        assert result["threshold_hours"] == 12.0

    # International short-haul (≤12h flight, threshold > 15h)
    def test_international_short_haul_at_threshold_not_significant(self):
        result = parse(check_baggage_threshold.invoke({
            "flight_type": "International", "flight_duration_hours": 10.0, "bag_delay_hours": 15.0
        }))
        assert result["is_significantly_delayed"] is False

    def test_international_short_haul_above_threshold_significant(self):
        result = parse(check_baggage_threshold.invoke({
            "flight_type": "International", "flight_duration_hours": 10.0, "bag_delay_hours": 15.1
        }))
        assert result["is_significantly_delayed"] is True

    # International long-haul (>12h flight, threshold > 30h)
    def test_international_long_haul_at_threshold_not_significant(self):
        result = parse(check_baggage_threshold.invoke({
            "flight_type": "International", "flight_duration_hours": 14.0, "bag_delay_hours": 30.0
        }))
        assert result["is_significantly_delayed"] is False

    def test_international_long_haul_above_threshold_significant(self):
        result = parse(check_baggage_threshold.invoke({
            "flight_type": "International", "flight_duration_hours": 14.0, "bag_delay_hours": 30.1
        }))
        assert result["is_significantly_delayed"] is True

    def test_returns_required_fields(self):
        result = parse(check_baggage_threshold.invoke({
            "flight_type": "Domestic (within US)", "flight_duration_hours": 3.0, "bag_delay_hours": 14.0
        }))
        assert all(k in result for k in ["is_significantly_delayed", "threshold_hours", "actual_delay_hours"])


# ── calculate_refund ──────────────────────────────────────────────────────────

class TestCalculateRefund:
    # Full refund
    def test_basic_ticket_refund(self):
        result = parse(calculate_refund.invoke({"ticket_price": 450.0}))
        assert result["refund_amount"] == 450.0
        assert result["refund_type"] == "full_refund"

    def test_includes_taxes_and_fees(self):
        result = parse(calculate_refund.invoke({
            "ticket_price": 400.0, "taxes_and_fees": 50.0
        }))
        assert result["refund_amount"] == 450.0

    def test_includes_ancillary_fees(self):
        result = parse(calculate_refund.invoke({
            "ticket_price": 400.0, "ancillary_fees": 30.0
        }))
        assert result["refund_amount"] == 430.0

    def test_subtracts_used_segments(self):
        result = parse(calculate_refund.invoke({
            "ticket_price": 500.0, "used_segments_value": 100.0
        }))
        assert result["refund_amount"] == 400.0

    def test_never_negative(self):
        result = parse(calculate_refund.invoke({
            "ticket_price": 50.0, "used_segments_value": 200.0
        }))
        assert result["refund_amount"] == 0.0

    def test_rounds_to_two_decimals(self):
        result = parse(calculate_refund.invoke({"ticket_price": 100.555}))
        assert result["refund_amount"] == round(100.555, 2)

    # Downgrade refund
    def test_downgrade_returns_fare_difference(self):
        result = parse(calculate_refund.invoke({
            "ticket_price": 0.0,
            "downgrade_from_class": "Business",
            "downgrade_to_class": "Economy",
            "downgrade_original_price": 1200.0,
            "downgrade_lower_price": 800.0,
        }))
        assert result["refund_amount"] == 400.0
        assert result["refund_type"] == "fare_difference"

    def test_downgrade_no_negative_refund(self):
        result = parse(calculate_refund.invoke({
            "ticket_price": 0.0,
            "downgrade_from_class": "Business",
            "downgrade_to_class": "Economy",
            "downgrade_original_price": 500.0,
            "downgrade_lower_price": 700.0,  # lower price is higher (weird edge case)
        }))
        assert result["refund_amount"] == 0.0

    def test_zero_ticket_price(self):
        result = parse(calculate_refund.invoke({"ticket_price": 0.0}))
        assert result["refund_amount"] == 0.0


# ── calculate_refund_timeline ─────────────────────────────────────────────────

class TestCalculateRefundTimeline:
    # Credit card — 7 business days
    def test_credit_card_business_days(self):
        result = parse(calculate_refund_timeline.invoke({"payment_method": "Credit Card"}))
        assert result["business_days"] == 7
        assert result["calendar_days"] is None

    def test_credit_card_case_insensitive(self):
        result = parse(calculate_refund_timeline.invoke({"payment_method": "credit card"}))
        assert result["business_days"] == 7

    # Non-credit card — 20 calendar days
    def test_debit_card_calendar_days(self):
        result = parse(calculate_refund_timeline.invoke({"payment_method": "Debit Card"}))
        assert result["calendar_days"] == 20
        assert result["business_days"] is None

    def test_cash_calendar_days(self):
        result = parse(calculate_refund_timeline.invoke({"payment_method": "Cash"}))
        assert result["calendar_days"] == 20

    def test_check_calendar_days(self):
        result = parse(calculate_refund_timeline.invoke({"payment_method": "Check"}))
        assert result["calendar_days"] == 20

    # Deadline calculation
    def test_credit_card_deadline_skips_weekends(self):
        # Monday + 7 business days = next Tuesday (skips 2 weekends)
        monday = "2026-03-16"
        result = parse(calculate_refund_timeline.invoke({
            "payment_method": "Credit Card", "event_date": monday
        }))
        deadline = date.fromisoformat(result["deadline_date"])
        start = date.fromisoformat(monday)
        # Count business days between start and deadline
        business_days_counted = sum(
            1 for i in range(1, (deadline - start).days + 1)
            if (start + timedelta(days=i)).weekday() < 5
        )
        assert business_days_counted == 7

    def test_cash_deadline_is_calendar_days(self):
        result = parse(calculate_refund_timeline.invoke({
            "payment_method": "Cash", "event_date": "2026-03-01"
        }))
        deadline = date.fromisoformat(result["deadline_date"])
        expected = date(2026, 3, 1) + timedelta(days=20)
        assert deadline == expected

    def test_invalid_date_returns_result_without_deadline(self):
        result = parse(calculate_refund_timeline.invoke({
            "payment_method": "Credit Card", "event_date": "not-a-date"
        }))
        assert "deadline_date" not in result or result.get("deadline_date") is None

    def test_no_event_date_returns_result(self):
        result = parse(calculate_refund_timeline.invoke({"payment_method": "Credit Card"}))
        assert "business_days" in result
