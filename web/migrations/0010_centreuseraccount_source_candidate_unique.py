from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("web", "0009_centreuseraccount_integration_fields"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="centreuseraccount",
            constraint=models.UniqueConstraint(
                fields=("source_system", "source_candidate_id"),
                name="web_centre_source_candidate_uniq",
            ),
        ),
    ]
