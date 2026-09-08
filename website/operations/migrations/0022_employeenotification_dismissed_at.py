from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0021_alter_estimate_external_status_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeenotification",
            name="dismissed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="employeenotification",
            index=models.Index(
                fields=["employee", "dismissed_at", "created_at"],
                name="operations__employe_433981_idx",
            ),
        ),
    ]
