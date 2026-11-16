from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("web", "0008_alter_failedloginattempt_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="centreuseraccount",
            name="source_system",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="centreuseraccount",
            name="source_user_id",
            field=models.PositiveBigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="centreuseraccount",
            name="source_candidate_id",
            field=models.PositiveBigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="centreuseraccount",
            name="exam_status",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="centreuseraccount",
            name="exam_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
