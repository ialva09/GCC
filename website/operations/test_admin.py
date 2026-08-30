from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client as DjangoClient
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .security import (
    ADMIN_GATE_EXPIRES_AT,
    ADMIN_GATE_NEXT,
    ADMIN_GATE_USER_ID,
)


class UnfoldAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser(
            username='admin-smoke',
            email='admin-smoke@example.com',
            password='admin-smoke-pass',
        )

    def setUp(self):
        self.browser = DjangoClient()
        self.login_admin()

    def login_admin(self):
        self.browser.logout()
        self.browser.force_login(self.admin_user)
        session = self.browser.session
        session[ADMIN_GATE_USER_ID] = str(self.admin_user.pk)
        session[ADMIN_GATE_EXPIRES_AT] = (timezone.now() + timedelta(minutes=10)).timestamp()
        session[ADMIN_GATE_NEXT] = reverse('admin:index')
        session.save()

    def test_native_admin_uses_unfold_and_grand_coast_branding(self):
        response = self.browser.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grand Coast Administration')
        self.assertContains(response, '/static/unfold/css/styles.css')
        self.assertContains(response, '/static/operations/images/gcc-logo.png')
        self.assertContains(response, 'Operations dashboard')
        self.assertContains(response, 'gcc-unfold-navigation-header')
        self.assertNotContains(response, 'stock-admin')
        self.assertNotContains(response, 'operations/css/admin.css')
        self.assertNotContains(response, 'demo')

    def test_unfold_admin_keeps_model_changelists_available(self):
        response = self.browser.get(reverse('admin:operations_lead_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Leads')

    def test_unfold_admin_actions_include_a_visible_run_control(self):
        response = self.browser.get(reverse('admin:auth_user_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="index"')
        self.assertContains(response, 'x-model="action"')
        self.assertContains(response, 'Run the selected action')

    def test_unfold_search_keeps_native_system_user_results(self):
        response = self.browser.get(reverse('admin:search'), {'s': 'admin-smoke'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse('admin:auth_user_change', args=(self.admin_user.pk,)),
        )

    def test_native_admin_home_matches_operations_visual_language(self):
        response = self.browser.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'gcc-admin-home-page')
        self.assertContains(response, 'gcc-admin-home')
        self.assertContains(response, 'GCC Inc.')
        self.assertContains(response, 'Open Operations')
        self.assertContains(response, 'Record management')

    def test_native_admin_login_matches_operations_visual_language(self):
        self.browser.logout()
        self.browser.post(
            reverse('admin:access'),
            {'identifier': self.admin_user.username},
        )
        response = self.browser.get(reverse('admin:login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'gcc-admin-login-page')
        self.assertContains(response, 'gcc-admin-login-shell')
        self.assertContains(response, 'Secure access')
        self.assertContains(response, 'Welcome back.')
        self.assertContains(response, '/static/operations/images/gcc-logo.png')
        self.assertNotContains(response, 'stock-admin')
        self.assertNotContains(response, 'demo')

    def test_non_staff_users_cannot_enter_native_admin(self):
        user = get_user_model().objects.create_user(
            username='not-staff',
            password='not-staff-pass',
        )
        self.browser.logout()
        self.browser.force_login(user)

        response = self.browser.get(reverse('admin:index'))

        self.assertEqual(response.status_code, 403)
