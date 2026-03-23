from django.contrib import admin
from .models import IndexVersion, Tenant, RefundDecision


@admin.register(IndexVersion)
class IndexVersionAdmin(admin.ModelAdmin):
    list_display = ['version', 'status', 'doc_count', 'created_at', 'activated_at']
    list_filter = ['status']
    readonly_fields = ['version', 'doc_count', 'doc_manifest', 'created_at', 'activated_at']


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['slug', 'name', 'is_active']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['slug', 'name']


@admin.register(RefundDecision)
class RefundDecisionAdmin(admin.ModelAdmin):
    list_display = ['id', 'tenant', 'index_version', 'decision', 'confidence', 'case_type', 'airline_name', 'created_at']
    list_filter = ['tenant', 'decision', 'confidence', 'index_version']
    search_fields = ['airline_name', 'flight_number', 'description']
