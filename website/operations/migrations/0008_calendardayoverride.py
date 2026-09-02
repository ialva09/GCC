import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('operations', '0007_lead_deleted_at_lead_deleted_by'),
    ]

    operations = [
        migrations.CreateModel(
            name='CalendarDayOverride',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date', models.DateField(unique=True)),
                ('status', models.CharField(choices=[('short', 'Short day'), ('closed', 'Closed')], max_length=10)),
                ('short_start', models.TimeField(blank=True, null=True)),
                ('short_end', models.TimeField(blank=True, null=True)),
                ('reason', models.CharField(blank=True, max_length=180)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_calendar_day_overrides', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['date'],
            },
        ),
    ]
