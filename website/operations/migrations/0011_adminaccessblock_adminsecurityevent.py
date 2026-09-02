import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0010_alter_employeenotification_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminAccessBlock',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('scope', models.CharField(choices=[('ip', 'IP address'), ('user', 'Administrator')], max_length=4)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('reason', models.CharField(blank=True, max_length=220)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_admin_access_blocks', to=settings.AUTH_USER_MODEL)),
                ('revoked_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revoked_admin_access_blocks', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='admin_access_blocks', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'constraints': [models.UniqueConstraint(condition=models.Q(('is_active', True), ('scope', 'ip')), fields=('ip_address',), name='unique_active_admin_ip_block'), models.UniqueConstraint(condition=models.Q(('is_active', True), ('scope', 'user')), fields=('user',), name='unique_active_admin_user_block'), models.CheckConstraint(condition=models.Q(models.Q(('ip_address__isnull', False), ('scope', 'ip'), ('user__isnull', True)), models.Q(('ip_address__isnull', True), ('scope', 'user'), ('user__isnull', False)), _connector='OR'), name='admin_block_matches_scope')],
            },
        ),
        migrations.CreateModel(
            name='AdminSecurityEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('event_type', models.CharField(choices=[('identifier_failure', 'Invalid admin identifier'), ('password_failure', 'Invalid admin password'), ('pin_failure', 'Invalid admin PIN'), ('otp_failure', 'Invalid authenticator code'), ('recovery_failure', 'Failed administration recovery'), ('password_reset_failure', 'Failed admin password reset'), ('login_success', 'Successful admin sign-in'), ('access_blocked', 'Blocked administration access')], max_length=32)),
                ('outcome', models.CharField(choices=[('failure', 'Failure'), ('success', 'Success'), ('blocked', 'Blocked')], max_length=12)),
                ('attempted_identifier', models.CharField(blank=True, max_length=254)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=500)),
                ('path', models.CharField(blank=True, max_length=255)),
                ('detail', models.CharField(blank=True, max_length=255)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('email_status', models.CharField(choices=[('not_required', 'Not required'), ('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed'), ('no_recipient', 'No recipient'), ('disabled', 'Disabled')], default='not_required', max_length=16)),
                ('email_attempt_count', models.PositiveIntegerField(default=0)),
                ('email_last_attempt_at', models.DateTimeField(blank=True, null=True)),
                ('email_sent_at', models.DateTimeField(blank=True, null=True)),
                ('email_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_admin_security_events', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='admin_security_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['ip_address', 'created_at'], name='admin_sec_event_ip_time'), models.Index(fields=['event_type', 'created_at'], name='admin_sec_event_type_time'), models.Index(fields=['outcome', 'created_at'], name='admin_sec_event_outcome_time'), models.Index(fields=['reviewed_at', 'created_at'], name='admin_sec_event_review_time')],
            },
        ),
    ]
