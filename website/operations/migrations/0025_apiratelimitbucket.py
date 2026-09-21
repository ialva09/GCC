from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0024_google_reviews"),
    ]

    operations = [
        migrations.CreateModel(
            name="APIRateLimitBucket",
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
                ("identity", models.CharField(max_length=191, unique=True)),
                ("window_started_at", models.DateTimeField()),
                ("request_count", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["window_started_at"],
                        name="api_rate_window_idx",
                    ),
                ],
            },
        ),
    ]
