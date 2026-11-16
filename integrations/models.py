from django.db import models


class IntegrationSyncLog(models.Model):
    RECEIVED = "received"
    CREATED = "created"
    UPDATED = "updated"
    REJECTED = "rejected"
    FAILED = "failed"

    STATUS_CHOICES = [
        (RECEIVED, "Received"),
        (CREATED, "Created"),
        (UPDATED, "Updated"),
        (REJECTED, "Rejected"),
        (FAILED, "Failed"),
    ]

    idempotency_key = models.CharField(max_length=255, unique=True)
    source_system = models.CharField(max_length=64)
    source_user_id = models.PositiveBigIntegerField(null=True, blank=True)
    source_candidate_id = models.PositiveBigIntegerField(null=True, blank=True)
    payload_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=RECEIVED)
    matched_by = models.CharField(max_length=32, blank=True, default="")
    centre_user_id = models.PositiveBigIntegerField(null=True, blank=True)
    http_status = models.PositiveIntegerField(null=True, blank=True)
    request_count = models.PositiveIntegerField(default=1)
    error_message = models.TextField(blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-received_at",)

    def __str__(self):
        return f"{self.source_system}:{self.idempotency_key} ({self.status})"
