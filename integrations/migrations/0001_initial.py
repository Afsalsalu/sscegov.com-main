from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="IntegrationSyncLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=255, unique=True)),
                ("source_system", models.CharField(max_length=64)),
                ("source_user_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("source_candidate_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("payload_digest", models.CharField(max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("received", "Received"),
                            ("created", "Created"),
                            ("updated", "Updated"),
                            ("rejected", "Rejected"),
                            ("failed", "Failed"),
                        ],
                        default="received",
                        max_length=20,
                    ),
                ),
                ("matched_by", models.CharField(blank=True, default="", max_length=32)),
                ("centre_user_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("http_status", models.PositiveIntegerField(blank=True, null=True)),
                ("request_count", models.PositiveIntegerField(default=1)),
                ("error_message", models.TextField(blank=True, default="")),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("-received_at",)},
        ),
    ]
