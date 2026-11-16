from django.contrib import admin

from .models import IntegrationSyncLog


@admin.register(IntegrationSyncLog)
class IntegrationSyncLogAdmin(admin.ModelAdmin):
    list_display = (
        "idempotency_key",
        "source_system",
        "source_candidate_id",
        "status",
        "matched_by",
        "centre_user_id",
        "http_status",
        "request_count",
        "received_at",
        "processed_at",
    )
    list_filter = ("source_system", "status", "matched_by", "http_status")
    search_fields = ("idempotency_key", "source_candidate_id", "source_user_id", "centre_user_id")
    readonly_fields = (
        "idempotency_key",
        "source_system",
        "source_user_id",
        "source_candidate_id",
        "payload_digest",
        "status",
        "matched_by",
        "centre_user_id",
        "http_status",
        "request_count",
        "error_message",
        "received_at",
        "processed_at",
        "updated_at",
    )
