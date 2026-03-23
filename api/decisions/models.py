"""Django models for storing refund decisions in SQLite."""

from django.db import models


class IndexVersion(models.Model):
    """
    Audit trail for every RAG index build.

    Answers: "Which regulations were in effect when decision #42 was made 3 months ago?"
    Link RefundDecision.index_version → this record → doc_manifest → exact file set.
    """

    STATUS_CHOICES = [
        ('building', 'Building'),   # build in progress
        ('active', 'Active'),       # currently serving queries
        ('failed', 'Failed'),       # build failed, never activated
        ('archived', 'Archived'),   # superseded by a newer version
    ]

    version = models.PositiveIntegerField(unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='building', db_index=True)
    doc_count = models.PositiveIntegerField(default=0)
    # Snapshot of data/bilgiler/ at build time: {filename: {size_bytes, mtime, sha256_prefix}}
    doc_manifest = models.JSONField(default=dict)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-version']

    def __str__(self):
        return f"IndexVersion v{self.version} ({self.status}, {self.doc_count} docs)"


class Tenant(models.Model):
    """An airline tenant. Each airline gets isolated decisions, cache, and config."""

    slug = models.SlugField(max_length=50, unique=True)   # e.g. "delta", "united"
    name = models.CharField(max_length=100)               # e.g. "Delta Air Lines"
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.slug})"


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

    # Which index version served this decision — enables regulation provenance queries
    index_version = models.ForeignKey(
        IndexVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decisions',
    )

    # Tenant (airline) — null for legacy / tenant-unaware requests
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='decisions',
        db_index=True,
    )

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
        indexes = [
            models.Index(fields=['tenant', '-created_at']),
        ]

    def __str__(self):
        tenant_label = self.tenant.slug if self.tenant else 'no-tenant'
        return f"#{self.id} [{tenant_label}] {self.decision} — {self.case_type} ({self.airline_name or 'unknown'})"
