from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core import management
from django.core import mail
from django.test import Client as DjangoClient
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import AdminRecoveryToken, AdminSecurityProfile


class PrivateAdminSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser(
            username="security-owner",
            email="security-owner@gcc.example.com",
            password="security-owner-pass",
        )

    def setUp(self):
        self.browser = DjangoClient()
        self.profile, _ = AdminSecurityProfile.objects.get_or_create(user=self.admin_user)
        self.profile.pin_enabled = False
        self.profile.pin_hash = ""
        self.profile.save(update_fields=["pin_enabled", "pin_hash", "updated_at"])
        TOTPDevice.objects.filter(user=self.admin_user).delete()

    def enter_password_login(self):
        gate = self.browser.post(
            reverse("admin:access"),
            {"identifier": self.admin_user.username},
        )
        self.assertRedirects(gate, reverse("admin:login"))
        login_response = self.browser.post(
            reverse("admin:login"),
            {
                "username": self.admin_user.username,
                "password": "security-owner-pass",
            },
        )
        self.assertRedirects(login_response, reverse("admin:index"))

    def test_legacy_admin_is_404_and_direct_login_cannot_bypass_gate(self):
        self.assertEqual(self.browser.get("/admin/").status_code, 404)
        response = self.browser.get(reverse("admin:login"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response['Location'],
            reverse('admin:access') + '?next=%2Fgccad%2Flogin%2F',
        )

    def test_pin_enabled_requires_pin_before_password_login(self):
        self.profile.pin_enabled = True
        self.profile.pin_hash = make_password("123456")
        self.profile.save(update_fields=["pin_enabled", "pin_hash", "updated_at"])

        identifier = self.browser.post(
            reverse("admin:access"),
            {"identifier": self.admin_user.email},
        )
        self.assertEqual(identifier.status_code, 302)
        self.assertIn(reverse("admin:access"), identifier["Location"])

        wrong_pin = self.browser.post(
            reverse("admin:access"),
            {"pin": "000000"},
        )
        self.assertEqual(wrong_pin.status_code, 200)
        self.assertContains(wrong_pin, "That PIN could not be verified.")

        correct_pin = self.browser.post(
            reverse("admin:access"),
            {"pin": "123456"},
        )
        self.assertRedirects(correct_pin, reverse("admin:login"))
        self.assertIsNone(self.browser.session.get("_auth_user_id"))

        login_response = self.browser.post(
            reverse("admin:login"),
            {
                "username": self.admin_user.username,
                "password": "security-owner-pass",
            },
        )
        self.assertRedirects(login_response, reverse("admin:index"))
        self.assertEqual(self.browser.session.get("_auth_user_id"), str(self.admin_user.pk))

    def test_gccad_entry_opens_branded_login_without_pin(self):
        response = self.browser.get(reverse('admin:index'), follow=True)

        self.assertContains(response, 'Welcome back.')
        self.assertNotContains(response, 'Before we begin.')
        self.assertNotContains(response, 'Enter your PIN.')

    def test_gccad_entry_starts_with_pin_when_admin_pin_is_enabled(self):
        self.profile.pin_enabled = True
        self.profile.pin_hash = make_password('123456')
        self.profile.save(update_fields=['pin_enabled', 'pin_hash', 'updated_at'])

        response = self.browser.get(reverse('admin:index'), follow=True)

        self.assertContains(response, 'Secure access')
        self.assertContains(response, 'Enter your PIN.')
        self.assertNotContains(response, 'Welcome back.')
        self.assertEqual(
            self.browser.session.get('gccad_gate_pending_pin'),
            str(self.admin_user.pk),
        )
    @override_settings(
        CLOUDFLARE_TURNSTILE_SITE_KEY="",
        CLOUDFLARE_TURNSTILE_SECRET_KEY="",
    )
    def test_public_login_rejects_superuser_without_creating_session(self):
        response = self.browser.post(
            reverse("operations:login"),
            {
                "username": self.admin_user.username,
                "password": "security-owner-pass",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct username and password.")
        self.assertNotContains(response, "%(username)s")
        self.assertIsNone(self.browser.session.get("_auth_user_id"))
        self.assertNotContains(response, "gccad")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_recovery_email_locks_after_five_unknown_emails_and_is_one_time(self):
        self.profile.pin_enabled = True
        self.profile.pin_hash = make_password("111111")
        self.profile.save(update_fields=["pin_enabled", "pin_hash", "updated_at"])
        device = TOTPDevice.objects.create(
            user=self.admin_user,
            name="Recovery test device",
            confirmed=True,
        )

        for attempt in range(4):
            response = self.browser.post(
                reverse("admin:recovery"),
                {"email": f"wrong-{attempt}@example.com"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "That email does not match an active administrator account.")
            self.assertContains(response, f"You have {4 - attempt} attempt")

        locked = self.browser.post(
            reverse("admin:recovery"),
            {"email": "wrong-final@example.com"},
        )
        self.assertEqual(locked.status_code, 429)
        self.assertIn("Too many attempts.", locked.content.decode())

        self.browser = DjangoClient()
        sent = self.browser.post(
            reverse("admin:recovery"),
            {"email": self.admin_user.email},
        )
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(r"/gccad/recover/([A-Za-z0-9_-]+)/", mail.outbox[0].body)
        self.assertIsNotNone(match)
        raw_token = match.group(1)
        token = AdminRecoveryToken.objects.get(user=self.admin_user)

        confirm = self.browser.get(
            reverse("admin:recovery-confirm", kwargs={"token": raw_token})
        )
        self.assertEqual(confirm.status_code, 200)
        complete = self.browser.post(
            reverse("admin:recovery-confirm", kwargs={"token": raw_token}),
            {"new_pin": "246810", "new_pin_confirmation": "246810"},
        )
        self.assertEqual(complete.status_code, 200)
        self.assertContains(complete, "Security reset")
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.pin_enabled)
        self.assertTrue(check_password("246810", self.profile.pin_hash))
        self.assertFalse(TOTPDevice.objects.filter(user=self.admin_user).exists())
        token.refresh_from_db()
        self.assertIsNotNone(token.used_at)
        self.assertIsNone(self.browser.session.get("_auth_user_id"))
        self.assertEqual(
            self.browser.get(
                reverse("admin:recovery-confirm", kwargs={"token": raw_token})
            ).status_code,
            410,
        )
        device.delete()

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_recovery_email_accepts_correct_email_before_lockout(self):
        for attempt in range(4):
            response = self.browser.post(
                reverse("admin:recovery"),
                {"email": f"wrong-before-match-{attempt}@example.com"},
            )
            self.assertEqual(response.status_code, 200)

        sent = self.browser.post(
            reverse("admin:recovery"),
            {"email": self.admin_user.email},
        )
        self.assertEqual(sent.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNone(self.browser.session.get("gccad_recovery_attempts"))
        self.assertIsNone(self.browser.session.get("gccad_recovery_locked_until"))

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        CLOUDFLARE_TURNSTILE_SITE_KEY="",
        CLOUDFLARE_TURNSTILE_SECRET_KEY="",
    )
    def test_admin_password_recovery_resets_password_without_changing_security_factors(self):
        page = self.browser.get(reverse("admin:index"), follow=True)
        self.assertContains(page, "Forgot your admin password?")
        reset_page = self.browser.get(reverse("admin:password-reset"))
        self.assertContains(reset_page, "/static/operations/css/unfold.css")
        self.assertContains(reset_page, "gcc-login-form-wrap")

        response = self.browser.post(
            reverse("admin:password-reset"),
            {"email": self.admin_user.email},
        )
        self.assertRedirects(response, reverse("admin:password-reset-done"))
        self.assertEqual(len(mail.outbox), 1)
        reset_url = next(
            line for line in mail.outbox[0].body.splitlines()
            if "/gccad/password-reset/confirm/" in line
        )
        confirm = self.browser.get(reset_url, follow=True)
        self.assertContains(confirm, "Choose a new password.")
        confirm_url = reset_url.replace(reset_url.rstrip("/").rsplit("/", 1)[-1], "set-password")
        reset = self.browser.post(
            confirm_url,
            {
                "new_password1": "admin-new-password-123",
                "new_password2": "admin-new-password-123",
            },
        )
        self.assertRedirects(reset, reverse("admin:password-reset-complete"))
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.check_password("admin-new-password-123"))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.pin_enabled)
        self.assertEqual(self.browser.get(reset_url).status_code, 200)
        self.assertContains(self.browser.get(reset_url), "That link has expired.")

        mail.outbox.clear()
        public_request = self.browser.post(
            reverse("operations:password-reset"),
            {"email": self.admin_user.email},
        )
        self.assertRedirects(public_request, reverse("operations:password-reset-done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_admin_password_recovery_locks_after_five_unknown_emails(self):
        reset_url = reverse("admin:password-reset")

        for attempt in range(4):
            response = self.browser.post(
                reset_url,
                {"email": f"unknown-admin-{attempt}@example.com"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "That email does not match an active administrator account.")
            remaining = 4 - attempt
            self.assertContains(response, f"You have {remaining} attempt")
        self.assertEqual(len(mail.outbox), 0)

        locked = self.browser.post(
            reset_url,
            {"email": "unknown-admin-final@example.com"},
        )
        self.assertEqual(locked.status_code, 429)
        self.assertContains(locked, "Too many password reset attempts.", status_code=429)
        self.assertEqual(self.browser.get(reset_url).status_code, 429)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_admin_password_recovery_accepts_correct_email_before_lockout(self):
        reset_url = reverse("admin:password-reset")
        for attempt in range(4):
            response = self.browser.post(
                reset_url,
                {"email": f"unknown-admin-before-match-{attempt}@example.com"},
            )
            self.assertEqual(response.status_code, 200)

        response = self.browser.post(reset_url, {"email": self.admin_user.email})
        self.assertRedirects(response, reverse("admin:password-reset-done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNone(self.browser.session.get("password_reset_attempts"))

    def test_totp_is_required_for_each_new_admin_session(self):
        device = TOTPDevice.objects.create(
            user=self.admin_user,
            name="Login test device",
            confirmed=True,
        )
        self.browser.post(
            reverse("admin:access"),
            {"identifier": self.admin_user.username},
        )
        password_response = self.browser.post(
            reverse("admin:login"),
            {
                "username": self.admin_user.username,
                "password": "security-owner-pass",
            },
        )
        self.assertRedirects(password_response, reverse("admin:otp"))
        otp_response = self.browser.get(reverse('admin:otp'))
        self.assertContains(otp_response, 'Authenticator verification')

        self.assertIsNone(self.browser.session.get("_auth_user_id"))

        valid = self.browser.post(
            reverse("admin:otp"),
            {"token": f"{totp(device.bin_key):06d}"},
        )
        self.assertRedirects(valid, reverse("admin:index"))
        self.assertEqual(self.browser.session.get("_auth_user_id"), str(self.admin_user.pk))
        self.assertEqual(self.browser.get(reverse("admin:index")).status_code, 200)

    def test_invalid_totp_code_does_not_authenticate(self):
        TOTPDevice.objects.create(
            user=self.admin_user,
            name="Invalid-code test device",
            confirmed=True,
        )
        self.browser.post(
            reverse("admin:access"),
            {"identifier": self.admin_user.username},
        )
        self.browser.post(
            reverse("admin:login"),
            {
                "username": self.admin_user.username,
                "password": "security-owner-pass",
            },
        )
        response = self.browser.post(reverse("admin:otp"), {"token": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not be verified")
        self.assertIsNone(self.browser.session.get("_auth_user_id"))

    def test_security_settings_use_simple_pin_controls(self):
        self.enter_password_login()
        page = self.browser.get(reverse("admin:security"))
        self.assertNotContains(page, "Current password")
        self.assertNotContains(page, "Current admin PIN")
        self.assertNotContains(page, "Current authenticator code")

        enable_pin = self.browser.post(
            reverse("admin:security"),
            {
                "action": "save-pin",
                "pin_enabled": "on",
                "new_pin": "123456",
                "new_pin_confirmation": "123456",
            },
        )
        self.assertRedirects(enable_pin, reverse("admin:security"))
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.pin_enabled)
        self.assertTrue(check_password("123456", self.profile.pin_hash))

        disable_pin = self.browser.post(
            reverse("admin:security"),
            {"action": "save-pin"},
        )
        self.assertRedirects(disable_pin, reverse("admin:security"))
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.pin_enabled)
        self.assertEqual(self.profile.pin_hash, "")

    def test_security_settings_can_enroll_totp_with_qr_scan(self):
        self.enter_password_login()
        page = self.browser.get(reverse("admin:security"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Authenticator app")
        self.assertContains(page, "No authenticator is connected")
        self.assertNotContains(page, "Current password")
        self.assertNotContains(page, "Current admin PIN")
        self.assertNotContains(page, "Current authenticator code")

        begin = self.browser.post(
            reverse("admin:security"),
            {
                "action": "begin-2fa",
            },
        )
        self.assertRedirects(begin, reverse("admin:security"))
        pending = TOTPDevice.objects.get(user=self.admin_user, confirmed=False)
        enrollment = self.browser.get(reverse("admin:security"))
        self.assertContains(enrollment, "I have scanned the QR code")
        self.assertContains(enrollment, "No code entry is needed here")
        self.assertNotContains(enrollment, "Manual setup key")
        self.assertNotContains(enrollment, 'name="token"')
        self.assertContains(enrollment, "data:image/svg+xml;base64")

        confirm = self.browser.post(
            reverse("admin:security"),
            {
                "action": "confirm-2fa",
            },
        )
        self.assertRedirects(confirm, reverse("admin:security"))
        pending.refresh_from_db()
        self.assertTrue(pending.confirmed)

        disable = self.browser.post(
            reverse("admin:security"),
            {"action": "disable-2fa"},
        )
        self.assertRedirects(disable, reverse("admin:security"))
        self.assertFalse(TOTPDevice.objects.filter(user=self.admin_user).exists())

    def test_logout_clears_admin_gate_and_otp_state(self):
        self.enter_password_login()
        session = self.browser.session
        session["gccad_gate_pending_pin"] = "pending"
        session["gccad_otp_pending_user"] = str(self.admin_user.pk)
        session["gccad_otp_verified_user"] = str(self.admin_user.pk)
        session.save()
        response = self.browser.get(reverse("admin:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('admin:access'))
        session = self.browser.session
        self.assertIsNone(session.get("_auth_user_id"))
        self.assertIsNone(session.get("gccad_gate_pending_pin"))
        self.assertIsNone(session.get("gccad_otp_pending_user"))
        self.assertIsNone(session.get("gccad_otp_verified_user"))

    def test_pwa_manifest_worker_and_public_offline_fallback(self):
        manifest = self.browser.get("/manifest.webmanifest")
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(manifest.json()["start_url"], "/")
        self.assertEqual(manifest.json()["scope"], "/")
        self.assertEqual(
            {icon["sizes"] for icon in manifest.json()["icons"]},
            {"192x192", "512x512"},
        )

        worker = self.browser.get("/service-worker.js")
        self.assertEqual(worker.status_code, 200)
        self.assertContains(worker, '"/gccad/"')
        self.assertContains(worker, '"/portal/"')
        self.assertNotContains(worker, "localStorage")

        public = self.browser.get(reverse("operations:home"))
        self.assertContains(public, "/manifest.webmanifest")
        self.assertContains(public, "pwa-register.js")
        self.assertEqual(self.browser.get("/offline/").status_code, 200)
