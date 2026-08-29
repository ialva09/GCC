from __future__ import annotations

import hashlib
import shutil
import tempfile
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import management
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client as DjangoClient
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import ProjectDocumentForm, ProjectForm
from .models import (
    Activity,
    Client as ClientRecord,
    ClientMessage,
    EmployeeInvite,
    EmployeeProfile,
    Estimate,
    EstimateLineItem,
    Lead,
    MediaAsset,
    Milestone,
    Project,
    ProjectDocument,
    ProjectUpdate,
    ScheduleEvent,
    SiteSettings,
    Task,
    TimeEntry,
)
from .services import (
    create_employee_invite,
    ensure_role_groups,
    find_employee_invite,
)


TEST_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix='gcc-platform-tests-'))


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class PlatformWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(
            username='platform-owner',
            password='owner-pass-123',
            first_name='Platform',
            last_name='Owner',
            email='owner@gcc.example.com',
            is_staff=True,
        )
        cls.manager = user_model.objects.create_user(
            username='platform-manager',
            password='manager-pass-123',
            first_name='Project',
            last_name='Manager',
            email='manager@gcc.example.com',
            is_staff=True,
        )
        cls.office = user_model.objects.create_user(
            username='platform-office',
            password='office-pass-123',
            first_name='Office',
            last_name='Coordinator',
            email='office@gcc.example.com',
            is_staff=True,
        )
        cls.field = user_model.objects.create_user(
            username='platform-field',
            password='field-pass-123',
            first_name='Field',
            last_name='Lead',
            email='field@gcc.example.com',
            is_staff=True,
        )
        roles = ensure_role_groups()
        cls.owner.groups.add(roles['Owner'])
        cls.manager.groups.add(roles['Manager'])
        cls.office.groups.add(roles['Office'])
        cls.field.groups.add(roles['Field'])
        for user, title in (
            (cls.owner, 'Owner'),
            (cls.manager, 'Manager'),
            (cls.office, 'Office coordinator'),
            (cls.field, 'Field lead'),
        ):
            EmployeeProfile.objects.create(user=user, job_title=title, phone='805-555-0100')

        cls.client_user = user_model.objects.create_user(
            username='platform-client',
            password='client-pass-123',
            first_name='Maya',
            last_name='Thompson',
            email='maya.platform@example.com',
        )
        cls.other_client_user = user_model.objects.create_user(
            username='platform-other-client',
            password='client-pass-123',
            first_name='Jordan',
            last_name='Lee',
            email='jordan.platform@example.com',
        )
        cls.client_record = ClientRecord.objects.create(
            name='Maya Thompson',
            email=cls.client_user.email,
            user=cls.client_user,
        )
        cls.other_client_record = ClientRecord.objects.create(
            name='Jordan Lee',
            email=cls.other_client_user.email,
            user=cls.other_client_user,
        )
        cls.lead = Lead.objects.create(
            client=cls.client_record,
            name='Maya Thompson',
            email=cls.client_user.email,
            service='Renovations',
            location='Ventura, CA',
            status=Lead.Status.QUALIFIED,
            assigned_to=cls.manager,
            created_by=cls.owner,
        )
        cls.estimate = Estimate.objects.create(
            number=9801,
            lead=cls.lead,
            client=cls.client_record,
            title='Platform kitchen scope',
            status=Estimate.Status.ACCEPTED,
            deposit_amount=Decimal('125.00'),
            accepted_at=timezone.now() - timedelta(days=1),
            accepted_by=cls.client_user,
            created_by=cls.owner,
        )
        EstimateLineItem.objects.create(
            estimate=cls.estimate,
            description='Cabinetry',
            quantity=Decimal('2.00'),
            unit_price=Decimal('100.00'),
        )
        cls.project = Project.objects.create(
            estimate=cls.estimate,
            lead=cls.lead,
            client=cls.client_record,
            title='Platform kitchen project',
            location='Ventura, CA',
            project_type='renovation',
            status=Project.Status.CONSTRUCTION,
            next_step='Complete rough-in',
            summary='A private test project.',
            fallback_image='operations/images/progress-kitchen.png',
            created_by=cls.owner,
        )
        cls.project.assigned_staff.add(cls.manager, cls.field)
        cls.milestone = Milestone.objects.create(
            project=cls.project,
            title='Rough-in',
            sort_order=1,
            is_complete=False,
        )
        cls.task = Task.objects.create(
            title='Field task for kitchen',
            description='Complete the field report.',
            project=cls.project,
            lead=cls.lead,
            milestone=cls.milestone,
            assigned_to=cls.field,
            priority=Task.Priority.HIGH,
            due_date=timezone.localdate(),
            created_by=cls.manager,
        )
        cls.other_project = Project.objects.create(
            client=cls.other_client_record,
            title='Other private project',
            location='Santa Barbara, CA',
            project_type='residential',
            status=Project.Status.PLANNING,
            fallback_image='operations/images/project-adu.png',
            created_by=cls.owner,
        )
        cls.other_task = Task.objects.create(
            title='Other client task',
            project=cls.other_project,
            assigned_to=cls.manager,
            created_by=cls.manager,
        )
        cls.field_event = ScheduleEvent.objects.create(
            title='Kitchen field visit',
            project=cls.project,
            task=cls.task,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=2),
            location='Ventura site',
            created_by=cls.manager,
        )
        cls.field_event.assignees.add(cls.field)
        cls.manager_event = ScheduleEvent.objects.create(
            title='Manager planning review',
            project=cls.other_project,
            start_at=timezone.now() + timedelta(days=2),
            end_at=timezone.now() + timedelta(days=2, hours=1),
            created_by=cls.manager,
        )
        cls.manager_event.assignees.add(cls.manager)
        cls.public_media = MediaAsset.objects.create(
            project=cls.project,
            title='Public kitchen image',
            fallback_image='operations/images/hero-kitchen.png',
            visibility=MediaAsset.Visibility.PUBLIC,
            uploaded_by=cls.owner,
        )
        cls.internal_media = MediaAsset.objects.create(
            project=cls.project,
            title='Internal field reference',
            fallback_image='operations/images/project-bathroom.png',
            visibility=MediaAsset.Visibility.INTERNAL,
            uploaded_by=cls.owner,
        )
        SiteSettings.objects.create(
            headline='Build with confidence.',
            subheadline='A clear path.',
            featured_title='Platform work',
            featured_body='Thoughtful construction.',
            featured_project=cls.project,
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.browser = DjangoClient()

    def login(self, user):
        self.browser.force_login(user)

    def test_roles_are_idempotent_and_field_isolated(self):
        ensure_role_groups()
        ensure_role_groups()
        self.assertEqual(Group.objects.filter(name__in=['Owner', 'Manager', 'Office', 'Field']).count(), 4)

        self.login(self.field)
        self.assertEqual(self.browser.get(reverse('operations:dashboard')).status_code, 403)
        team_response = self.browser.get(reverse('operations:team'))
        self.assertEqual(team_response.status_code, 200)
        self.assertContains(team_response, self.project.title)
        self.assertNotContains(team_response, self.other_project.title)
        task_response = self.browser.get(reverse('operations:team-section', kwargs={'section': 'tasks'}))
        self.assertContains(task_response, self.task.title)
        self.assertNotContains(task_response, self.other_task.title)
        calendar_response = self.browser.get(reverse('operations:team-section', kwargs={'section': 'calendar'}))
        self.assertContains(calendar_response, self.field_event.title)
        self.assertNotContains(calendar_response, self.manager_event.title)
        self.assertEqual(
            self.browser.get(reverse('admin:index')).status_code,
            302,
        )

    def test_client_only_reaches_own_portal_records(self):
        self.login(self.client_user)
        self.assertEqual(self.browser.get(reverse('operations:dashboard')).status_code, 403)
        self.assertEqual(self.browser.get(reverse('operations:team')).status_code, 403)
        portal_response = self.browser.get(
            reverse('operations:portal'),
            {'project': self.other_project.pk},
        )
        self.assertEqual(portal_response.status_code, 200)
        self.assertContains(portal_response, self.project.title)
        self.assertNotContains(portal_response, self.other_project.title)
        self.assertEqual(self.browser.get(reverse('admin:index')).status_code, 302)

    def test_field_employees_cannot_open_client_portal_preview(self):
        self.login(self.field)
        self.assertEqual(self.browser.get(reverse('operations:portal')).status_code, 403)

    def test_field_employee_cannot_change_active_status_from_profile(self):
        self.login(self.field)
        response = self.browser.post(
            reverse('operations:team-profile-update', kwargs={'pk': self.field.employee_profile.pk}),
            {
                'job_title': 'Updated field lead',
                'phone': '805-555-0199',
                'is_active': '',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.field.employee_profile.refresh_from_db()
        self.assertTrue(self.field.employee_profile.is_active)

    def test_employee_invite_is_one_time_and_expired_links_are_rejected(self):
        group = Group.objects.get(name='Field')
        invite, raw_token = create_employee_invite(
            email='new.field@gcc.example.com',
            first_name='New',
            last_name='Field',
            group=group,
            actor=self.owner,
        )
        invite_url = reverse('operations:employee-invite', kwargs={'token': raw_token})
        self.assertEqual(self.browser.get(invite_url).status_code, 200)
        response = self.browser.post(
            invite_url,
            {
                'username': 'new-field',
                'first_name': 'New',
                'last_name': 'Field',
                'password1': 'new-field-password-123',
                'password2': 'new-field-password-123',
            },
        )
        self.assertRedirects(response, reverse('operations:team'))
        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)
        new_user = get_user_model().objects.get(username='new-field')
        self.assertTrue(new_user.is_staff)
        self.assertTrue(new_user.groups.filter(name='Field').exists())
        self.assertTrue(EmployeeProfile.objects.filter(user=new_user).exists())
        self.assertEqual(self.browser.get(invite_url).status_code, 410)

        expired_raw = 'expired-employee-token'
        expired = EmployeeInvite.objects.create(
            email='expired@gcc.example.com',
            group=group,
            token_hash=hashlib.sha256(expired_raw.encode()).hexdigest(),
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(expired.is_usable)
        self.assertEqual(
            self.browser.get(reverse('operations:employee-invite', kwargs={'token': expired_raw})).status_code,
            410,
        )

    def test_manager_password_reset_link_changes_password_once(self):
        invite, raw_token = create_employee_invite(
            email=self.manager.email,
            first_name=self.manager.first_name,
            last_name=self.manager.last_name,
            group=Group.objects.get(name='Manager'),
            actor=self.owner,
            employee=self.manager.employee_profile,
            purpose=EmployeeInvite.Purpose.PASSWORD_RESET,
        )
        reset_url = reverse('operations:employee-invite', kwargs={'token': raw_token})
        response = self.browser.post(
            reset_url,
            {
                'password1': 'manager-new-password-123',
                'password2': 'manager-new-password-123',
            },
        )
        self.assertRedirects(response, reverse('operations:team'))
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.check_password('manager-new-password-123'))
        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)
        self.assertIsNone(find_employee_invite(raw_token))

    def test_lead_assignment_conversion_and_estimate_requires_client(self):
        unconverted = Lead.objects.create(
            name='Unconverted Lead',
            email='unconverted@example.com',
            service='Restoration',
            location='Ojai, CA',
        )
        self.login(self.manager)
        before = Estimate.objects.count()
        blocked = self.browser.post(
            reverse('operations:estimate-create'),
            {
                'lead': unconverted.pk,
                'title': 'Blocked estimate',
                'deposit_amount': '0.00',
            },
        )
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(Estimate.objects.count(), before)

        assignment = self.browser.post(
            reverse('operations:lead-assign', kwargs={'pk': unconverted.pk}),
            {'assigned_to': self.field.pk},
        )
        self.assertEqual(assignment.status_code, 302)
        unconverted.refresh_from_db()
        self.assertEqual(unconverted.assigned_to_id, self.field.id)
        conversion = self.browser.post(
            reverse('operations:lead-convert-client', kwargs={'pk': unconverted.pk}),
        )
        self.assertEqual(conversion.status_code, 302)
        unconverted.refresh_from_db()
        self.assertIsNotNone(unconverted.client_id)

        created = self.browser.post(
            reverse('operations:estimate-create'),
            {
                'lead': unconverted.pk,
                'title': 'Allowed estimate',
                'deposit_amount': '0.00',
            },
        )
        self.assertEqual(created.status_code, 302)
        self.assertTrue(Estimate.objects.filter(title='Allowed estimate', client=unconverted.client).exists())

    def test_lead_derived_project_requires_accepted_estimate(self):
        lead = Lead.objects.create(
            name='Needs approval',
            email='needs-approval@example.com',
            service='Renovation',
            location='Ventura, CA',
            client=self.client_record,
        )
        form = ProjectForm(
            {
                'title': 'Blocked lead project',
                'client': self.client_record.pk,
                'lead': lead.pk,
                'assigned_staff': [self.field.pk],
                'location': 'Ventura, CA',
                'project_type': 'renovation',
                'status': Project.Status.PLANNING,
                'next_step': 'Review',
                'summary': '',
                'is_published': 'on',
                'start_date': '',
                'target_date': '',
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn('accepted estimate', str(form.errors).lower())

        lead.estimates.create(
            number=9901,
            client=self.client_record,
            title='Approved scope',
            status=Estimate.Status.ACCEPTED,
        )
        form = ProjectForm(form.data)
        self.assertTrue(form.is_valid())

    def test_task_assignment_status_filters_and_activity(self):
        self.login(self.manager)
        create_response = self.browser.post(
            reverse('operations:task-create'),
            {
                'title': 'Assign concrete inspection',
                'description': 'Check the slab before the next phase.',
                'lead': self.lead.pk,
                'project': self.project.pk,
                'milestone': self.milestone.pk,
                'assigned_to': self.field.pk,
                'watchers': [self.office.pk],
                'status': Task.Status.OPEN,
                'priority': Task.Priority.URGENT,
                'due_date': timezone.localdate().isoformat(),
            },
        )
        self.assertEqual(create_response.status_code, 302)
        new_task = Task.objects.get(title='Assign concrete inspection')
        self.assertTrue(new_task.watchers.filter(pk=self.office.pk).exists())
        self.assertTrue(Activity.objects.filter(message='Task created', detail=new_task.title).exists())

        self.login(self.field)
        status_response = self.browser.post(
            reverse('operations:team-task-status', kwargs={'pk': self.task.pk}),
            {'status': Task.Status.COMPLETE},
        )
        self.assertEqual(status_response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.COMPLETE)
        self.assertIsNotNone(self.task.completed_at)
        denied = self.browser.post(
            reverse('operations:team-task-status', kwargs={'pk': self.other_task.pk}),
            {'status': Task.Status.COMPLETE},
        )
        self.assertEqual(denied.status_code, 403)

        filtered = self.browser.get(
            reverse('operations:team-section', kwargs={'section': 'tasks'}),
            {
                'priority': Task.Priority.HIGH,
                'project_filter': self.project.pk,
                'due': 'today',
            },
        )
        self.assertContains(filtered, self.task.title)
        self.assertNotContains(filtered, self.other_task.title)

    def test_schedule_creation_and_employee_visibility(self):
        start = timezone.now() + timedelta(days=5)
        end = start + timedelta(hours=2)
        self.login(self.manager)
        response = self.browser.post(
            reverse('operations:schedule-create'),
            {
                'title': 'Material delivery',
                'assignees': [self.field.pk],
                'project': self.project.pk,
                'task': self.task.pk,
                'start_at': start.strftime('%Y-%m-%dT%H:%M'),
                'end_at': end.strftime('%Y-%m-%dT%H:%M'),
                'location': 'Ventura site',
                'notes': 'Confirm delivery window.',
            },
        )
        self.assertEqual(response.status_code, 302)
        event = ScheduleEvent.objects.get(title='Material delivery')
        self.assertTrue(event.assignees.filter(pk=self.field.pk).exists())
        self.assertContains(
            self.browser.get(reverse('operations:dashboard-section', kwargs={'section': 'calendar'})),
            event.title,
        )
        self.assertContains(
            self.browser.get(reverse('operations:team-section', kwargs={'section': 'calendar'})),
            event.title,
        )

    def test_clock_in_out_duplicate_prevention_and_pacific_display(self):
        fixed_clock_in = datetime(2026, 8, 28, 16, 15, tzinfo=datetime_timezone.utc)
        fixed_entry = TimeEntry.objects.create(
            employee=self.field,
            project=self.project,
            task=self.task,
            clock_in=fixed_clock_in,
            clock_out=fixed_clock_in + timedelta(hours=1),
        )
        self.login(self.field)
        response = self.browser.get(reverse('operations:team-section', kwargs={'section': 'time'}))
        self.assertContains(response, '9:15 AM')
        self.assertContains(response, 'America/Los_Angeles')

        clock_in = self.browser.post(
            reverse('operations:team-time-clock'),
            {'project': self.project.pk, 'task': self.task.pk, 'note': 'Site arrival'},
        )
        self.assertEqual(clock_in.status_code, 302)
        active = TimeEntry.objects.get(employee=self.field, clock_out__isnull=True)
        self.assertEqual(active.project_id, self.project.id)
        clock_out = self.browser.post(reverse('operations:team-time-clock'), {'note': 'Leaving site'})
        self.assertEqual(clock_out.status_code, 302)
        active.refresh_from_db()
        self.assertIsNotNone(active.clock_out)
        fixed_entry.delete()
        open_entry = TimeEntry.objects.create(employee=self.field, clock_in=timezone.now())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TimeEntry.objects.create(employee=self.field, clock_in=timezone.now())
        open_entry.delete()

    def test_document_validation_and_protected_client_delivery(self):
        invalid = SimpleUploadedFile('plans.exe', b'bad', content_type='application/octet-stream')
        form = ProjectDocumentForm(
            {
                'project': self.project.pk,
                'title': 'Bad file',
                'category': 'Plans',
                'visibility': ProjectDocument.Visibility.CLIENT,
            },
            {'file': invalid},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Upload a PDF', str(form.errors))

        client_document = ProjectDocument.objects.create(
            project=self.project,
            title='Client plans',
            category='Plans',
            visibility=ProjectDocument.Visibility.CLIENT,
            uploaded_by=self.owner,
        )
        client_document.file.save('client-plans.pdf', ContentFile(b'pdf bytes'), save=True)
        internal_document = ProjectDocument.objects.create(
            project=self.project,
            title='Internal notes',
            category='Notes',
            visibility=ProjectDocument.Visibility.INTERNAL,
            uploaded_by=self.owner,
        )
        internal_document.file.save('internal-notes.pdf', ContentFile(b'internal bytes'), save=True)

        client_url = reverse('operations:document-file', kwargs={'pk': client_document.pk})
        internal_url = reverse('operations:document-file', kwargs={'pk': internal_document.pk})
        self.login(self.client_user)
        self.assertEqual(self.browser.get(client_url).status_code, 200)
        self.assertEqual(self.browser.get(internal_url).status_code, 403)
        self.browser.force_login(self.other_client_user)
        self.assertEqual(self.browser.get(client_url).status_code, 403)
        self.login(self.field)
        self.assertEqual(self.browser.get(internal_url).status_code, 200)

    def test_two_way_client_messages_and_public_visibility(self):
        self.login(self.client_user)
        client_message_response = self.browser.post(
            reverse('operations:portal-message'),
            {'project': self.project.pk, 'body': 'Can we review the finish schedule?'},
        )
        self.assertEqual(client_message_response.status_code, 302)
        client_message = ClientMessage.objects.get(body='Can we review the finish schedule?')
        self.assertEqual(client_message.sent_by_id, self.client_user.id)
        self.assertFalse(client_message.is_read)

        self.login(self.office)
        staff_response = self.browser.post(
            reverse('operations:staff-message-reply', kwargs={'client_pk': self.client_record.pk}),
            {'project': self.project.pk, 'body': 'Yes, the team will share it today.'},
        )
        self.assertEqual(staff_response.status_code, 302)
        staff_message = ClientMessage.objects.get(body='Yes, the team will share it today.')
        self.assertTrue(staff_message.sent_by.is_staff)
        self.login(self.client_user)
        self.browser.get(reverse('operations:portal'))
        staff_message.refresh_from_db()
        self.assertTrue(staff_message.is_read)

        settings = SiteSettings.objects.get(pk=1)
        settings.google_review_url = 'https://g.page/r/grandcoast/review'
        settings.save(update_fields=['google_review_url', 'updated_at'])
        public_response = self.browser.get(reverse('operations:home'))
        self.assertContains(public_response, 'Review us on Google')
        detail_response = self.browser.get(reverse('operations:project-detail', kwargs={'pk': self.project.pk}))
        self.assertContains(detail_response, self.public_media.title)
        self.assertNotContains(detail_response, self.internal_media.title)

    def test_client_cannot_mutate_portal_acceptance_as_staff_preview(self):
        self.login(self.owner)
        response = self.browser.post(
            reverse('operations:portal-accept-estimate', kwargs={'pk': self.estimate.pk}),
        )
        self.assertEqual(response.status_code, 403)


class SeedOperationsTests(TestCase):
    def test_seed_operations_is_idempotent_and_creates_roles(self):
        management.call_command('seed_operations', verbosity=0)
        counts = {
            'services': __import__('operations.models', fromlist=['Service']).Service.objects.count(),
            'process_steps': __import__('operations.models', fromlist=['ProcessStep']).ProcessStep.objects.count(),
            'clients': ClientRecord.objects.count(),
            'leads': Lead.objects.count(),
            'estimates': Estimate.objects.count(),
            'projects': Project.objects.count(),
            'tasks': Task.objects.count(),
        }
        management.call_command('seed_operations', verbosity=0)
        self.assertEqual(Group.objects.filter(name__in=['Owner', 'Manager', 'Office', 'Field']).count(), 4)
        self.assertEqual(
            {key: model_count for key, model_count in counts.items()},
            {
                'services': __import__('operations.models', fromlist=['Service']).Service.objects.count(),
                'process_steps': __import__('operations.models', fromlist=['ProcessStep']).ProcessStep.objects.count(),
                'clients': ClientRecord.objects.count(),
                'leads': Lead.objects.count(),
                'estimates': Estimate.objects.count(),
                'projects': Project.objects.count(),
                'tasks': Task.objects.count(),
            },
        )
