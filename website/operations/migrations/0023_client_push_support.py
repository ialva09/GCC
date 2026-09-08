from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0022_employeenotification_dismissed_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mobilepushdevice",
            name="employee",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="mobile_push_devices",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="mobilepushdevice",
            name="client",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="mobile_push_devices",
                to="operations.client",
            ),
        ),
        migrations.AddConstraint(
            model_name="mobilepushdevice",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(employee__isnull=False, client__isnull=True)
                    | models.Q(employee__isnull=True, client__isnull=False)
                ),
                name="mobile_push_device_one_owner",
            ),
        ),
        migrations.AlterField(
            model_name="pushdelivery",
            name="notification",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="push_deliveries",
                to="operations.employeenotification",
            ),
        ),
        migrations.AddField(
            model_name="pushdelivery",
            name="client_notification",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="push_deliveries",
                to="operations.clientnotification",
            ),
        ),
        migrations.AddConstraint(
            model_name="pushdelivery",
            constraint=models.UniqueConstraint(
                fields=("client_notification", "device"),
                name="unique_client_notification_push_device",
            ),
        ),
        migrations.AddConstraint(
            model_name="pushdelivery",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(notification__isnull=False, client_notification__isnull=True)
                    | models.Q(notification__isnull=True, client_notification__isnull=False)
                ),
                name="push_delivery_one_notification",
            ),
        ),
    ]
