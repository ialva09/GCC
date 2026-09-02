from __future__ import annotations

import base64
import hashlib
import io
import secrets
from datetime import timedelta

import segno
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import AdminRecoveryToken, AdminSecurityProfile


ADMIN_GATE_USER_ID = "gccad_gate_user_id"
ADMIN_GATE_EXPIRES_AT = "gccad_gate_expires_at"
ADMIN_GATE_NEXT = "gccad_gate_next"
ADMIN_GATE_PENDING_PIN = "gccad_gate_pending_pin"
ADMIN_GATE_PIN_ATTEMPTS = "gccad_gate_pin_attempts"
ADMIN_GATE_LOCKED_UNTIL = "gccad_gate_locked_until"
ADMIN_OTP_PENDING_USER = "gccad_otp_pending_user"
ADMIN_OTP_PENDING_NEXT = "gccad_otp_pending_next"
ADMIN_OTP_ATTEMPTS = "gccad_otp_attempts"
ADMIN_OTP_VERIFIED_USER = "gccad_otp_verified_user"
ADMIN_OTP_ENROLLMENT_DEVICE = "gccad_otp_enrollment_device"
ADMIN_RECOVERY_ATTEMPTS = "gccad_recovery_attempts"
ADMIN_RECOVERY_LOCKED_UNTIL = "gccad_recovery_locked_until"
PASSWORD_RESET_ATTEMPTS = "password_reset_attempts"
PASSWORD_RESET_LOCKED_UNTIL = "password_reset_locked_until"

ADMIN_GATE_TTL = timedelta(minutes=10)
ADMIN_RECOVERY_TTL = timedelta(minutes=30)
ADMIN_RECOVERY_LOCKOUT = timedelta(minutes=15)
ADMIN_PIN_ATTEMPT_LIMIT = 5
ADMIN_OTP_ATTEMPT_LIMIT = 5
ADMIN_RECOVERY_ATTEMPT_LIMIT = 5
PASSWORD_RESET_ATTEMPT_LIMIT = 5
PASSWORD_RESET_LOCKOUT = timedelta(minutes=15)


def is_active_admin(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_active
        and user.is_staff
        and user.is_superuser
    )


def admin_security_profile(user):
    profile, _ = AdminSecurityProfile.objects.get_or_create(user=user)
    return profile


def confirmed_totp_device(user):
    return (
        TOTPDevice.objects.filter(user=user, confirmed=True)
        .order_by("-last_used_at", "-created_at")
        .first()
    )


def has_totp_enabled(user):
    return confirmed_totp_device(user) is not None


def pin_is_enabled(user):
    profile = admin_security_profile(user)
    return bool(profile.pin_enabled and profile.pin_hash)


def verify_admin_pin(user, pin):
    profile = admin_security_profile(user)
    return bool(profile.pin_enabled and profile.pin_hash and check_password(pin or "", profile.pin_hash))


def resolve_admin_identifier(identifier):
    value = (identifier or "").strip()
    if not value:
        return None
    user_model = get_user_model()
    admins = user_model.objects.filter(is_active=True, is_staff=True, is_superuser=True)
    username_match = admins.filter(username__iexact=value)
    if username_match.count() == 1:
        return username_match.first()
    email_match = admins.filter(email__iexact=value)
    if email_match.count() == 1:
        return email_match.first()
    return None


def _safe_admin_next(value):
    candidate = (value or "").strip()
    if candidate and candidate.startswith(settings.ADMIN_URL_PREFIX) and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={},
        require_https=False,
    ):
        return candidate
    return reverse("admin:index")


def gate_is_valid(request, user=None):
    stored_user = request.session.get(ADMIN_GATE_USER_ID)
    expires_at = request.session.get(ADMIN_GATE_EXPIRES_AT)
    if not stored_user or not expires_at:
        return False
    try:
        active = float(expires_at) > timezone.now().timestamp()
    except (TypeError, ValueError):
        active = False
    if not active:
        clear_gate(request)
        return False
    return user is None or str(stored_user) == str(user.pk)


def gate_next(request):
    return _safe_admin_next(request.session.get(ADMIN_GATE_NEXT))


def set_gate(request, user, next_url=None):
    request.session[ADMIN_GATE_USER_ID] = str(user.pk)
    request.session[ADMIN_GATE_EXPIRES_AT] = (timezone.now() + ADMIN_GATE_TTL).timestamp()
    request.session[ADMIN_GATE_NEXT] = _safe_admin_next(next_url)
    request.session.pop(ADMIN_GATE_PENDING_PIN, None)
    request.session.pop(ADMIN_GATE_PIN_ATTEMPTS, None)
    request.session.modified = True


def clear_gate(request):
    for key in (
        ADMIN_GATE_USER_ID,
        ADMIN_GATE_EXPIRES_AT,
        ADMIN_GATE_NEXT,
        ADMIN_GATE_PENDING_PIN,
        ADMIN_GATE_PIN_ATTEMPTS,
    ):
        request.session.pop(key, None)
    request.session.modified = True


def admin_gate_locked(request):
    locked_until = request.session.get(ADMIN_GATE_LOCKED_UNTIL)
    if not locked_until:
        return False
    try:
        locked = float(locked_until) > timezone.now().timestamp()
    except (TypeError, ValueError):
        locked = False
    if not locked:
        request.session.pop(ADMIN_GATE_LOCKED_UNTIL, None)
        request.session.pop(ADMIN_GATE_PIN_ATTEMPTS, None)
        request.session.modified = True
    return locked


def register_gate_failure(request):
    attempts = int(request.session.get(ADMIN_GATE_PIN_ATTEMPTS, 0)) + 1
    request.session[ADMIN_GATE_PIN_ATTEMPTS] = attempts
    if attempts >= ADMIN_PIN_ATTEMPT_LIMIT:
        request.session[ADMIN_GATE_LOCKED_UNTIL] = (
            timezone.now() + ADMIN_RECOVERY_LOCKOUT
        ).timestamp()
    request.session.modified = True


def begin_otp_challenge(request, user, next_url=None):
    request.session[ADMIN_OTP_PENDING_USER] = str(user.pk)
    request.session[ADMIN_OTP_PENDING_NEXT] = _safe_admin_next(next_url)
    request.session[ADMIN_OTP_ATTEMPTS] = 0
    request.session.modified = True


def pending_otp_user(request):
    user_id = request.session.get(ADMIN_OTP_PENDING_USER)
    if not user_id:
        return None
    user = get_user_model().objects.filter(
        pk=user_id,
        is_active=True,
        is_staff=True,
        is_superuser=True,
    ).first()
    if user is None:
        clear_otp_challenge(request)
    return user


def pending_otp_next(request):
    return _safe_admin_next(request.session.get(ADMIN_OTP_PENDING_NEXT))


def clear_otp_challenge(request):
    for key in (
        ADMIN_OTP_PENDING_USER,
        ADMIN_OTP_PENDING_NEXT,
        ADMIN_OTP_ATTEMPTS,
    ):
        request.session.pop(key, None)
    request.session.modified = True


def clear_admin_challenges(request):
    clear_gate(request)
    clear_otp_challenge(request)
    for key in (
        ADMIN_GATE_LOCKED_UNTIL,
        ADMIN_OTP_VERIFIED_USER,
        ADMIN_OTP_ENROLLMENT_DEVICE,
    ):
        request.session.pop(key, None)
    request.session.modified = True


def mark_otp_verified(request, user, device):
    request.session[ADMIN_OTP_VERIFIED_USER] = str(user.pk)
    request.session.modified = True
    otp_login(request, device)


def otp_is_verified(request, user):
    return str(request.session.get(ADMIN_OTP_VERIFIED_USER, "")) == str(user.pk)


def register_otp_failure(request):
    attempts = int(request.session.get(ADMIN_OTP_ATTEMPTS, 0)) + 1
    request.session[ADMIN_OTP_ATTEMPTS] = attempts
    request.session.modified = True
    return attempts >= ADMIN_OTP_ATTEMPT_LIMIT


def begin_totp_enrollment(user):
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    return TOTPDevice.objects.create(
        user=user,
        name="Grand Coast authenticator",
        confirmed=False,
        digits=6,
    )


def remove_totp_devices(user):
    TOTPDevice.objects.filter(user=user).delete()


def totp_qr_data_uri(device):
    qr = segno.make(device.config_url, micro=False)
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", scale=5)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def totp_manual_key(device):
    return base64.b32encode(device.bin_key).decode("ascii").rstrip("=")


@transaction.atomic
def create_admin_recovery_token(request, user):
    now = timezone.now()
    AdminRecoveryToken.objects.filter(
        user=user,
        purpose=AdminRecoveryToken.Purpose.SECURITY_RESET,
        used_at__isnull=True,
    ).update(used_at=now)
    raw_token = secrets.token_urlsafe(32)
    token = AdminRecoveryToken.objects.create(
        user=user,
        purpose=AdminRecoveryToken.Purpose.SECURITY_RESET,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=now + ADMIN_RECOVERY_TTL,
    )
    recovery_url = request.build_absolute_uri(
        reverse("admin:recovery-confirm", kwargs={"token": raw_token})
    )
    send_mail(
        "Grand Coast administration security recovery",
        (
            f"Use this one-time link to reset your Grand Coast admin PIN and disable "
            f"authenticator 2FA:\n\n{recovery_url}\n\n"
            f"This link expires in 30 minutes and will not sign you in automatically."
        ),
        getattr(settings, "DEFAULT_FROM_EMAIL", "webmaster@localhost"),
        [user.email],
    )
    return token


def find_admin_recovery_token(raw_token):
    if not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token = AdminRecoveryToken.objects.select_related("user").filter(
        token_hash=token_hash,
        purpose=AdminRecoveryToken.Purpose.SECURITY_RESET,
    ).first()
    return token if token and token.is_usable and is_active_admin(token.user) else None


@transaction.atomic
def consume_admin_recovery_token(raw_token):
    token_hash = hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()
    token = (
        AdminRecoveryToken.objects.select_for_update()
        .select_related("user")
        .filter(
            token_hash=token_hash,
            purpose=AdminRecoveryToken.Purpose.SECURITY_RESET,
        )
        .first()
    )
    if token is None or not token.is_usable or not is_active_admin(token.user):
        return None
    token.used_at = timezone.now()
    token.save(update_fields=["used_at"])
    return token


def recovery_is_locked(request):
    locked_until = request.session.get(ADMIN_RECOVERY_LOCKED_UNTIL)
    if not locked_until:
        return False
    try:
        locked = float(locked_until) > timezone.now().timestamp()
    except (TypeError, ValueError):
        locked = False
    if not locked:
        request.session.pop(ADMIN_RECOVERY_LOCKED_UNTIL, None)
        request.session.pop(ADMIN_RECOVERY_ATTEMPTS, None)
        request.session.modified = True
    return locked


def register_recovery_failure(request):
    attempts = int(request.session.get(ADMIN_RECOVERY_ATTEMPTS, 0)) + 1
    request.session[ADMIN_RECOVERY_ATTEMPTS] = attempts
    if attempts >= ADMIN_RECOVERY_ATTEMPT_LIMIT:
        request.session[ADMIN_RECOVERY_LOCKED_UNTIL] = (
            timezone.now() + ADMIN_RECOVERY_LOCKOUT
        ).timestamp()
    request.session.modified = True
    return attempts


def clear_recovery_failures(request):
    request.session.pop(ADMIN_RECOVERY_ATTEMPTS, None)
    request.session.pop(ADMIN_RECOVERY_LOCKED_UNTIL, None)
    request.session.modified = True


def password_reset_is_locked(request):
    locked_until = request.session.get(PASSWORD_RESET_LOCKED_UNTIL)
    if not locked_until:
        return False
    try:
        locked = float(locked_until) > timezone.now().timestamp()
    except (TypeError, ValueError):
        locked = False
    if not locked:
        request.session.pop(PASSWORD_RESET_LOCKED_UNTIL, None)
        request.session.pop(PASSWORD_RESET_ATTEMPTS, None)
        request.session.modified = True
    return locked


def register_password_reset_failure(request):
    attempts = int(request.session.get(PASSWORD_RESET_ATTEMPTS, 0)) + 1
    request.session[PASSWORD_RESET_ATTEMPTS] = attempts
    if attempts >= PASSWORD_RESET_ATTEMPT_LIMIT:
        request.session[PASSWORD_RESET_LOCKED_UNTIL] = (
            timezone.now() + PASSWORD_RESET_LOCKOUT
        ).timestamp()
    request.session.modified = True
    return attempts


def clear_password_reset_failures(request):
    request.session.pop(PASSWORD_RESET_ATTEMPTS, None)
    request.session.pop(PASSWORD_RESET_LOCKED_UNTIL, None)
    request.session.modified = True


class PasswordResetThrottleMixin:
    password_reset_reject_unknown_email = False

    def _password_reset_locked_response(self, form=None):
        return self.render_to_response(
            self.get_context_data(
                form=form or self.get_form(),
                password_reset_locked=True,
            ),
            status=429,
        )

    def get(self, request, *args, **kwargs):
        if password_reset_is_locked(request):
            return self._password_reset_locked_response()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if password_reset_is_locked(request):
            return self._password_reset_locked_response()
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        users = tuple(form.get_users(form.cleaned_data["email"]))
        if users:
            clear_password_reset_failures(self.request)
        else:
            attempts = register_password_reset_failure(self.request)
            if password_reset_is_locked(self.request):
                return self._password_reset_locked_response(form)
            if self.password_reset_reject_unknown_email:
                remaining = PASSWORD_RESET_ATTEMPT_LIMIT - attempts
                attempt_word = "attempt" if remaining == 1 else "attempts"
                form.add_error(
                    "email",
                    (
                        "That email does not match an active administrator account. "
                        f"You have {remaining} {attempt_word} remaining."
                    ),
                )
                return self.form_invalid(form)
        return super().form_valid(form)


def revoke_user_sessions(user):
    for session in Session.objects.all():
        if str(session.get_decoded().get("_auth_user_id", "")) == str(user.pk):
            session.delete()


def reset_admin_security(user, new_pin):
    profile = admin_security_profile(user)
    profile.pin_enabled = True
    profile.pin_hash = make_password(new_pin)
    profile.save(update_fields=["pin_enabled", "pin_hash", "updated_at"])
    remove_totp_devices(user)
