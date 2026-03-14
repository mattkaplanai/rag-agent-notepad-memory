"""Django REST Framework serializers for the refund API."""

from rest_framework import serializers
from .models import RefundDecision


class RefundRequestSerializer(serializers.Serializer):
    """Serializer for incoming refund analysis requests."""

    case_type = serializers.ChoiceField(choices=[
        'Flight Cancellation',
        'Schedule Change / Significant Delay',
        'Downgrade to Lower Class',
        'Baggage Lost or Delayed',
        'Ancillary Service Not Provided',
        '24-Hour Cancellation (within 24h of booking)',
    ])
    flight_type = serializers.ChoiceField(choices=[
        'Domestic (within US)',
        'International',
    ])
    ticket_type = serializers.ChoiceField(choices=[
        'Refundable',
        'Non-refundable',
    ])
    payment_method = serializers.ChoiceField(choices=[
        'Credit Card', 'Debit Card', 'Cash', 'Check', 'Airline Miles', 'Other',
    ])
    accepted_alternative = serializers.ChoiceField(choices=[
        'No — I did not accept any alternative',
        'Yes — I accepted a rebooked flight',
        'Yes — I accepted a travel voucher / credit',
        'Yes — I accepted other compensation (miles, etc.)',
        'Yes — I traveled on the flight anyway',
    ])
    description = serializers.CharField(min_length=10, max_length=2000)


class RefundDecisionSerializer(serializers.ModelSerializer):
    """Serializer for refund decision responses."""

    class Meta:
        model = RefundDecision
        fields = '__all__'


class RefundDecisionListSerializer(serializers.ModelSerializer):
    """Compact serializer for listing decisions."""

    class Meta:
        model = RefundDecision
        fields = [
            'id', 'case_type', 'flight_type', 'airline_name',
            'flight_number', 'decision', 'confidence',
            'processing_time_seconds', 'created_at',
        ]
