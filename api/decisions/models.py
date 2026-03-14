"""Django models for storing refund decisions in SQLite."""

from django.db import models


class RefundDecision(models.Model):
    """A single refund decision stored in the database."""

    DECISION_CHOICES = [
        ('APPROVED', 'Approved'),
        ('DENIED', 'Denied'),
        ('PARTIAL', 'Partial'),
        ('ERROR', 'Error'),
    ]

    CONFIDENCE_CHOICES = [
        ('HIGH', 'High'),
        ('MEDIUM', 'Medium'),
        ('LOW', 'Low'),
    ]

    # Input fields
    case_type = models.CharField(max_length=100)
    flight_type = models.CharField(max_length=50)
    ticket_type = models.CharField(max_length=50)
    payment_method = models.CharField(max_length=50)
    accepted_alternative = models.CharField(max_length=200)
    description = models.TextField()

    # Classifier extracted fields
    airline_name = models.CharField(max_length=100, blank=True, default='')
    flight_number = models.CharField(max_length=20, blank=True, default='')
    flight_date = models.CharField(max_length=20, blank=True, default='')
    flight_duration_hours = models.FloatField(null=True, blank=True)
    delay_hours = models.FloatField(null=True, blank=True)
    bag_delay_hours = models.FloatField(null=True, blank=True)
    ticket_price = models.FloatField(null=True, blank=True)

    # Decision output
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES)
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES)
    analysis_steps = models.JSONField(default=list)
    reasons = models.JSONField(default=list)
    applicable_regulations = models.JSONField(default=list)
    refund_details = models.JSONField(null=True, blank=True)
    passenger_action_items = models.JSONField(default=list)
    tools_used = models.JSONField(default=list)
    decision_letter = models.TextField(blank=True, null=True, default='')

    # Full raw result (for debugging)
    raw_result = models.JSONField(default=dict)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    processing_time_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"#{self.id} {self.decision} — {self.case_type} ({self.airline_name or 'unknown'})"
