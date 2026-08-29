from __future__ import annotations

import hashlib
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as DjangoClient
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import MediaUploadForm
from .models import (
    Activity,
    Client,
    ClientInvite,
    Estimate,
    EstimateLineItem,
    Lead,
    MediaAsset,
    Milestone,
    ProcessStep,
    Project,
    ProjectUpdate,
    Service,
    SiteSettings,
)
from .services import create_client_invite


TEST_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="gcc-operations-tests-"))


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class OperationsWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.staff = user_model.objects.create_user(username="owner", password="owner-pass")
        cls.staff.is_staff = True
        cls.staff.save(update_fields=["is_staff"])
        cls.client_user = user_model.objects.create_user(
            username="client-a",
            password="client-pass",
            first_name="Maya",
            last_name="Thompson",
            email="maya@example.com",
        )
        cls.other_client_user = user_model.objects.create_user(
            username="client-b",
            password="client-pass",
            first_name="Jordan",
            last_name="Lee",
            email="jordan@example.com",
        )
        cls.client_record = Client.objects.create(
            name="Maya Thompson",
            email="maya@example.com",
            user=cls.client_user,
        )
        cls.other_client_record = Client.objects.create(
            name="Jordan Lee",
            email="jordan@example.com",
            user=cls.other_client_user,
        )
        cls.lead = Lead.objects.create(
            client=cls.client_record,
            name="Maya Thompson",
            email="maya@example.com",
            service="Renovations",
            location="Ventura, CA",
            status=Lead.Status.NEW,
            created_by=cls.staff,
        )
        cls.estimate = Estimate.objects.create(
            lead=cls.lead,
            client=cls.client_record,
            title="Kitchen scope",
            status=Estimate.Status.DRAFT,
            deposit_amount=Decimal("50.00"),
            created_by=cls.staff,
        )
        cls.line = EstimateLineItem.objects.create(
            estimate=cls.estimate,
            description="Cabinetry",
            quantity=Decimal("2.00"),
            unit_price=Decimal("100.00"),
            sort_order=1,
        )
        cls.project = Project.objects.create(
            estimate=cls.estimate,
            lead=cls.lead,
            client=cls.client_record,
            title="Kitchen project",
            location="Ventura, CA",
            project_type="renovation",
            status=Project.Status.PLANNING,
            fallback_image="operations/images/progress-kitchen.png",
            created_by=cls.staff,
        )
        cls.milestone = Milestone.objects.create(
            project=cls.project,
            title="Walkthrough",
            sort_order=1,
        )
        cls.other_project = Project.objects.create(
            client=cls.other_client_record,
            title="Private other project",
            location="Santa Barbara, CA",
            project_type="residential",
            fallback_image="operations/images/project-adu.png",
            created_by=cls.staff,
        )
        cls.public_media = MediaAsset.objects.create(
            project=cls.project,
            title="Public reference",
            fallback_image="operations/images/hero-kitchen.png",
            visibility=MediaAsset.Visibility.PUBLIC,
            uploaded_by=cls.staff,
        )
        cls.client_media = MediaAsset.objects.create(
            project=cls.project,
            title="Client progress",
            fallback_image="operations/images/progress-kitchen.png",
            visibility=MediaAsset.Visibility.CLIENT,
            uploaded_by=cls.staff,
        )
        cls.internal_media = MediaAsset.objects.create(
            project=cls.project,
            title="Internal reference",
            fallback_image="operations/images/project-bathroom.png",
            visibility=MediaAsset.Visibility.INTERNAL,
            uploaded_by=cls.staff,
        )
        Service.objects.create(
            slug="renovations",
            title="Renovations",
            description="Renovation work.",
            image_path="operations/images/hero-kitchen.png",
            sort_order=1,
        )
        ProcessStep.objects.create(
            key="inquire",
            title="Start together",
            description="A clear first step.",
            sort_order=1,
        )
        SiteSettings.objects.create(
            headline="Build with confidence.",
            subheadline="A clear path.",
            featured_title="Featured work",
            featured_body="Thoughtful details.",
            featured_project=cls.project,
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.browser = DjangoClient()

    def login_staff(self):
        self.browser.force_login(self.staff)

    def login_client(self):
        self.browser.force_login(self.client_user)

    def test_public_contact_form_creates_real_lead(self):
        response = self.browser.post(
            reverse("operations:contact"),
            {
                "first_name": "New",
                "last_name": "Homeowner",
                "email": "new.homeowner@example.com",
                "phone": "805-555-0100",
                "project_type": "Restoration",
                "location": "Ojai, CA",
                "message": "Please help us plan the first phase.",
            },
        )
        self.assertRedirects(response, reverse("operations:contact"))
        lead = Lead.objects.get(email="new.homeowner@example.com")
        self.assertEqual(lead.name, "New Homeowner")
        self.assertEqual(lead.status, Lead.Status.NEW)
        self.assertTrue(Activity.objects.filter(lead=lead, message="New lead received").exists())

    def test_staff_dashboard_is_protected_from_clients_and_anonymous_users(self):
        response = self.browser.get(reverse("operations:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("operations:login"), response["Location"])
        self.login_client()
        self.assertEqual(self.browser.get(reverse("operations:dashboard")).status_code, 403)
        self.login_staff()
        response = self.browser.get(reverse("operations:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("operations:portal"))
        self.assertContains(response, reverse("admin:index"))

    def test_admin_search_routes_operations_records_to_dashboard(self):
        self.login_staff()

        lead_response = self.browser.get(reverse('admin:search'), {'s': 'Maya'})
        self.assertEqual(lead_response.status_code, 200)
        leads_url = reverse('operations:dashboard-section', kwargs={'section': 'leads'})
        estimates_url = reverse('operations:dashboard-section', kwargs={'section': 'estimates'})
        projects_url = reverse('operations:dashboard-section', kwargs={'section': 'projects'})
        self.assertContains(lead_response, 'Maya Thompson')
        self.assertContains(lead_response, f'{leads_url}?lead={self.lead.pk}')
        self.assertContains(lead_response, f'{estimates_url}?estimate={self.estimate.pk}')
        self.assertContains(lead_response, f'{projects_url}?project={self.project.pk}')
        self.assertNotContains(lead_response, '/admin/operations/lead/')

        media_response = self.browser.get(reverse('admin:search'), {'s': 'Public reference'})
        self.assertContains(media_response, 'Public reference')
        media_url = reverse('operations:dashboard-section', kwargs={'section': 'media'})
        self.assertContains(
            media_response,
            f'{media_url}?media_project={self.project.pk}',
        )

        content_response = self.browser.get(reverse('admin:search'), {'s': 'Renovation work'})
        self.assertContains(content_response, 'Renovations')
        self.assertContains(
            content_response,
            reverse('operations:dashboard-section', kwargs={'section': 'content'}),
        )

    def test_admin_search_is_staff_only(self):
        anonymous_response = self.browser.get(reverse('admin:search'), {'s': 'Maya'})
        self.assertEqual(anonymous_response.status_code, 302)
        self.assertIn(reverse('admin:login'), anonymous_response['Location'])

        self.login_client()
        client_response = self.browser.get(reverse('admin:search'), {'s': 'Maya'})
        self.assertEqual(client_response.status_code, 302)
        self.assertIn(reverse('admin:login'), client_response['Location'])

    def test_dashboard_lead_search_matches_client_fields(self):
        self.login_staff()
        response = self.browser.get(
            reverse('operations:dashboard-section', kwargs={'section': 'leads'}),
            {'q': 'maya@example.com'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Maya Thompson')

    def test_lead_status_and_priority_are_persistent(self):
        self.login_staff()
        status_response = self.browser.post(
            reverse("operations:lead-status", kwargs={"pk": self.lead.pk}),
            {"status": Lead.Status.QUALIFIED},
        )
        self.assertEqual(status_response.status_code, 302)
        priority_response = self.browser.post(
            reverse("operations:lead-priority", kwargs={"pk": self.lead.pk}),
        )
        self.assertEqual(priority_response.status_code, 302)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.QUALIFIED)
        self.assertTrue(self.lead.priority)

    def test_estimate_line_items_recalculate_on_server(self):
        self.login_staff()
        response = self.browser.post(
            reverse("operations:estimate-update", kwargs={"pk": self.estimate.pk}),
            {
                "title": "Updated kitchen scope",
                "status": Estimate.Status.DRAFT,
                "deposit_amount": "75.00",
                "notes": "Updated notes",
                "lines-TOTAL_FORMS": "2",
                "lines-INITIAL_FORMS": "1",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "50",
                "lines-0-id": str(self.line.pk),
                "lines-0-description": "Cabinetry revised",
                "lines-0-quantity": "2.00",
                "lines-0-unit_price": "125.00",
                "lines-0-sort_order": "1",
                "lines-1-id": "",
                "lines-1-description": "Hardware",
                "lines-1-quantity": "1.00",
                "lines-1-unit_price": "25.00",
                "lines-1-sort_order": "2",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.estimate.refresh_from_db()
        self.assertEqual(self.estimate.title, "Updated kitchen scope")
        self.assertEqual(self.estimate.total, Decimal("275.00"))
        self.assertEqual(self.estimate.deposit_amount, Decimal("75.00"))
        self.assertEqual(self.estimate.line_items.count(), 2)

    def test_estimate_cannot_remove_last_line_item(self):
        self.login_staff()
        response = self.browser.post(
            reverse("operations:estimate-update", kwargs={"pk": self.estimate.pk}),
            {
                "title": "Kitchen scope",
                "status": Estimate.Status.DRAFT,
                "deposit_amount": "0.00",
                "notes": "",
                "lines-TOTAL_FORMS": "2",
                "lines-INITIAL_FORMS": "1",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "50",
                "lines-0-id": str(self.line.pk),
                "lines-0-description": "Cabinetry",
                "lines-0-quantity": "2.00",
                "lines-0-unit_price": "100.00",
                "lines-0-sort_order": "1",
                "lines-0-DELETE": "on",
                "lines-1-id": "",
                "lines-1-description": "",
                "lines-1-quantity": "1.00",
                "lines-1-unit_price": "0.00",
                "lines-1-sort_order": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(EstimateLineItem.objects.filter(pk=self.line.pk).exists())

    def test_estimate_status_timestamps_and_accepted_lock(self):
        self.login_staff()
        response = self.browser.post(reverse("operations:estimate-send", kwargs={"pk": self.estimate.pk}))
        self.assertEqual(response.status_code, 302)
        self.estimate.refresh_from_db()
        self.assertEqual(self.estimate.status, Estimate.Status.SENT)
        self.assertIsNotNone(self.estimate.sent_at)
        old_title = self.estimate.title
        self.estimate.status = Estimate.Status.ACCEPTED
        self.estimate.save(update_fields=["status", "updated_at"])
        locked = self.browser.post(
            reverse("operations:estimate-update", kwargs={"pk": self.estimate.pk}),
            {"title": "Should not change"},
        )
        self.assertEqual(locked.status_code, 302)
        self.estimate.refresh_from_db()
        self.assertEqual(self.estimate.title, old_title)

    def test_client_can_accept_assigned_estimate(self):
        self.estimate.status = Estimate.Status.SENT
        self.estimate.sent_at = timezone.now()
        self.estimate.save(update_fields=["status", "sent_at", "updated_at"])
        self.login_client()
        response = self.browser.post(
            reverse("operations:portal-accept-estimate", kwargs={"pk": self.estimate.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.estimate.refresh_from_db()
        self.assertEqual(self.estimate.status, Estimate.Status.ACCEPTED)
        self.assertEqual(self.estimate.accepted_by_id, self.client_user.id)
        self.assertIsNotNone(self.estimate.accepted_at)

    def test_accepted_estimate_creates_project_and_default_milestones(self):
        estimate = Estimate.objects.create(
            lead=self.lead,
            client=self.client_record,
            title="Accepted addition",
            status=Estimate.Status.ACCEPTED,
            created_by=self.staff,
        )
        EstimateLineItem.objects.create(
            estimate=estimate,
            description="Planning",
            quantity=1,
            unit_price=100,
        )
        self.login_staff()
        response = self.browser.post(reverse("operations:estimate-project", kwargs={"pk": estimate.pk}))
        self.assertEqual(response.status_code, 302)
        project = Project.objects.get(estimate=estimate)
        self.assertEqual(project.client_id, self.client_record.id)
        self.assertEqual(project.status, Project.Status.PLANNING)
        self.assertEqual(project.milestones.count(), 5)

    def test_project_milestones_and_updates_persist_with_visibility(self):
        self.login_staff()
        self.browser.post(
            reverse("operations:milestone-toggle", kwargs={"pk": self.milestone.pk}),
            {"is_complete": "on"},
        )
        update_response = self.browser.post(
            reverse("operations:project-add-update", kwargs={"pk": self.project.pk}),
            {"title": "Selections are ready", "body": "Please review the finish direction.", "visibility": ProjectUpdate.Visibility.CLIENT},
        )
        self.assertEqual(update_response.status_code, 302)
        self.milestone.refresh_from_db()
        self.assertTrue(self.milestone.is_complete)
        update = ProjectUpdate.objects.get(project=self.project, title="Selections are ready")
        self.assertEqual(update.visibility, ProjectUpdate.Visibility.CLIENT)

    def test_client_portal_only_shows_assigned_project(self):
        self.login_client()
        response = self.browser.get(
            reverse("operations:portal"),
            {"project": self.other_project.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.title)
        self.assertNotContains(response, self.other_project.title)

    def test_private_media_requires_correct_authenticated_client(self):
        self.public_media.file.save("public-reference.jpg", ContentFile(b"public bytes"), save=True)
        self.client_media.file.save("client-progress.jpg", ContentFile(b"client bytes"), save=True)
        self.internal_media.file.save("internal-reference.jpg", ContentFile(b"internal bytes"), save=True)
        public_url = reverse("operations:media-file", kwargs={"pk": self.public_media.pk})
        client_url = reverse("operations:media-file", kwargs={"pk": self.client_media.pk})
        internal_url = reverse("operations:media-file", kwargs={"pk": self.internal_media.pk})
        direct_storage_url = f"{settings.MEDIA_URL}{self.client_media.file.name}"
        self.assertEqual(self.browser.get(public_url).status_code, 200)
        self.assertEqual(self.browser.get(direct_storage_url).status_code, 404)
        self.login_client()
        self.assertEqual(self.browser.get(client_url, follow=True).status_code, 200)
        self.assertEqual(self.browser.get(internal_url).status_code, 403)
        self.browser.force_login(self.other_client_user)
        self.assertEqual(self.browser.get(client_url).status_code, 403)
        self.login_staff()
        self.assertEqual(self.browser.get(internal_url).status_code, 200)

    def test_media_upload_form_rejects_unsupported_extension(self):
        upload = SimpleUploadedFile("malware.exe", b"not an image", content_type="application/octet-stream")
        form = MediaUploadForm(
            {"project": str(self.project.pk), "visibility": MediaAsset.Visibility.CLIENT},
            {"files": [upload]},
            project_queryset=Project.objects.all(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Upload a JPG", str(form.errors))

    def test_valid_media_upload_is_persisted(self):
        self.login_staff()
        upload = SimpleUploadedFile("progress.jpg", b"fake image bytes", content_type="image/jpeg")
        response = self.browser.post(
            reverse("operations:media-upload"),
            {"project": str(self.project.pk), "visibility": MediaAsset.Visibility.CLIENT, "files": [upload]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(MediaAsset.objects.filter(project=self.project, title="progress").exists())

    def test_content_updates_appear_on_public_site(self):
        self.login_staff()
        response = self.browser.post(
            reverse("operations:content-update"),
            {
                "headline": "Build with more clarity.",
                "subheadline": "Updated supporting copy.",
                "featured_title": "Updated featured work",
                "featured_body": "Updated featured description.",
                "service_renovations_title": "Renovation planning",
                "service_renovations_copy": "Updated service copy.",
                "step_inquire": "Begin with a walkthrough",
            },
        )
        self.assertEqual(response.status_code, 302)
        public_response = self.browser.get(reverse("operations:home"))
        self.assertContains(public_response, "Build with more clarity.")
        self.assertContains(public_response, "Renovation planning")

    def test_invite_is_one_time_and_expires(self):
        invite_client = Client.objects.create(name="Invite Client", email="invite@example.com")
        invite, raw_token = create_client_invite(invite_client, actor=self.staff)
        invite_response = self.browser.get(reverse("operations:client-invite", kwargs={"token": raw_token}))
        self.assertEqual(invite_response.status_code, 200)
        accept_response = self.browser.post(
            reverse("operations:client-invite", kwargs={"token": raw_token}),
            {
                "username": "jordan.portal",
                "first_name": "Jordan",
                "last_name": "Lee",
                "password1": "strong-client-password",
                "password2": "strong-client-password",
            },
        )
        self.assertEqual(accept_response.status_code, 302)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)
        self.assertEqual(self.browser.get(reverse("operations:client-invite", kwargs={"token": raw_token})).status_code, 410)

        expired_raw = "expired-token"
        expired = ClientInvite.objects.create(
            client=self.client_record,
            token_hash=hashlib.sha256(expired_raw.encode()).hexdigest(),
            expires_at=timezone.now() - timedelta(days=1),
            created_by=self.staff,
        )
        self.assertFalse(expired.is_usable)
        self.assertEqual(self.browser.get(reverse("operations:client-invite", kwargs={"token": expired_raw})).status_code, 410)
