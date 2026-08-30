from __future__ import annotations

from functools import update_wrapper
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.hashers import make_password
from django.contrib.auth.views import LoginView
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django_otp.plugins.otp_totp.models import TOTPDevice
from unfold.sites import UnfoldAdminSite

from .forms import (
    AdminGateIdentifierForm,
    AdminOtpForm,
    AdminPinForm,
    AdminPinSettingsForm,
    AdminRecoveryRequestForm,
    AdminRecoveryResetForm,
    AdminTwoFactorStartForm,
    GrandCoastAdminAuthenticationForm,
)
from .security import (
    ADMIN_GATE_PENDING_PIN,
    ADMIN_GATE_NEXT,
    ADMIN_OTP_ENROLLMENT_DEVICE,
    admin_gate_locked,
    admin_security_profile,
    begin_otp_challenge,
    begin_totp_enrollment,
    clear_admin_challenges,
    clear_gate,
    clear_otp_challenge,
    consume_admin_recovery_token,
    confirmed_totp_device,
    create_admin_recovery_token,
    find_admin_recovery_token,
    gate_is_valid,
    gate_next,
    has_totp_enabled,
    is_active_admin,
    mark_otp_verified,
    otp_is_verified,
    pending_otp_next,
    pending_otp_user,
    pin_is_enabled,
    register_gate_failure,
    register_otp_failure,
    register_recovery_failure,
    recovery_is_locked,
    remove_totp_devices,
    reset_admin_security,
    revoke_user_sessions,
    resolve_admin_identifier,
    set_gate,
    totp_qr_data_uri,
    verify_admin_pin,
)



class GrandCoastAdminLoginView(LoginView):
    admin_site = None

    def form_valid(self, form):
        user = form.get_user()
        if not is_active_admin(user) or not gate_is_valid(self.request, user):
            clear_gate(self.request)
            form.add_error(None, form.error_messages["invalid_login"])
            return self.form_invalid(form)

        next_url = gate_next(self.request)
        device = confirmed_totp_device(user)
        if device is not None:
            begin_otp_challenge(self.request, user, next_url)
            return redirect(reverse("admin:otp"))

        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        self.request.session.pop("gccad_otp_verified_user", None)
        return HttpResponseRedirect(next_url)

    def get_success_url(self):
        return gate_next(self.request)


class GrandCoastAdminSite(UnfoldAdminSite):
    site_header = "Grand Coast Administration"
    site_title = "Grand Coast Administration"
    index_title = "Administration"

    def has_permission(self, request):
        return bool(
            request.user.is_authenticated
            and request.user.is_active
            and request.user.is_staff
            and request.user.is_superuser
        )

    def _access_url(self, next_url=None):
        url = reverse("admin:access")
        if next_url:
            url = f"{url}?{urlencode({REDIRECT_FIELD_NAME: next_url})}"
        return url

    def _single_admin_user(self):
        admins = list(get_user_model().objects.filter(
            is_active=True,
            is_staff=True,
            is_superuser=True,
        ))
        return admins[0] if len(admins) == 1 else None


    def _render_admin_page(self, request, template_name, context=None, **kwargs):
        page_context = self.each_context(request)
        page_context.update(context or {})
        return render(request, template_name, page_context, **kwargs)

    def admin_view(self, view, cacheable=False):
        def inner(request, *args, **kwargs):
            if not self.has_permission(request):
                if request.user.is_authenticated:
                    return HttpResponseForbidden("Administration access is restricted.")
                return redirect(self._access_url(request.get_full_path()))
            if not gate_is_valid(request, request.user):
                return redirect(self._access_url(request.get_full_path()))
            if has_totp_enabled(request.user) and not otp_is_verified(request, request.user):
                logout(request)
                clear_admin_challenges(request)
                return redirect(self._access_url(request.get_full_path()))
            return view(request, *args, **kwargs)

        if not cacheable:
            inner = never_cache(inner)
        if not getattr(view, "csrf_exempt", False):
            inner = csrf_protect(inner)
        return update_wrapper(inner, view)

    def login(self, request, extra_context=None):
        requested_next = request.GET.get(REDIRECT_FIELD_NAME) or request.POST.get(REDIRECT_FIELD_NAME)
        if not gate_is_valid(request):
            return redirect(self._access_url(requested_next or request.get_full_path()))
        if request.method == "GET" and self.has_permission(request):
            if has_totp_enabled(request.user) and not otp_is_verified(request, request.user):
                logout(request)
                clear_admin_challenges(request)
            else:
                return HttpResponseRedirect(gate_next(request))

        redirect_url = gate_next(request)
        context = {
            **self.each_context(request),
            "title": "Log in",
            "subtitle": None,
            "app_path": request.get_full_path(),
            "username": request.user.get_username(),
            REDIRECT_FIELD_NAME: redirect_url,
        }
        context.update(extra_context or {})
        defaults = {
            "extra_context": context,
            "authentication_form": GrandCoastAdminAuthenticationForm,
            "template_name": self.login_template or "admin/login.html",
            "admin_site": self,
        }
        request.current_app = self.name
        return GrandCoastAdminLoginView.as_view(**defaults)(request)

    def logout(self, request, extra_context=None):
        logout(request)
        clear_admin_challenges(request)
        return redirect(self._access_url())

    def get_urls(self):
        custom_urls = [
            path("access/", self.access, name="access"),
            path("otp/", self.otp, name="otp"),
            path("recover/", self.recovery, name="recovery"),
            path(
                "recover/<str:token>/",
                self.recovery_confirm,
                name="recovery-confirm",
            ),
            path(
                "security/",
                self.admin_view(self.security_settings),
                name="security",
            ),
        ]
        return custom_urls + super().get_urls()

    def access(self, request):
        if request.user.is_authenticated and not self.has_permission(request):
            return HttpResponseForbidden("Administration access is restricted.")

        next_url = request.GET.get(REDIRECT_FIELD_NAME) or request.POST.get(REDIRECT_FIELD_NAME)
        next_url = next_url or reverse("admin:index")
        if request.method == "GET" and request.session.get(ADMIN_GATE_PENDING_PIN) is None:
            default_admin = self._single_admin_user()
            if default_admin is not None:
                if pin_is_enabled(default_admin):
                    request.session[ADMIN_GATE_PENDING_PIN] = str(default_admin.pk)
                    request.session[ADMIN_GATE_NEXT] = next_url
                    request.session.modified = True
                else:
                    set_gate(request, default_admin, next_url)
                    return redirect("admin:login")

        if gate_is_valid(request):
            return redirect("admin:login")

        if admin_gate_locked(request):
            return self._render_admin_page(
                request,
                "admin/access.html",
                {
                    "title": "Administration access",
                    "site_title": self.site_title,
                    "locked": True,
                    "next": next_url,
                },
                status=429,
            )

        pending_user_id = request.session.get(ADMIN_GATE_PENDING_PIN)
        pending_user = (
            get_user_model()
            .objects.filter(
                pk=pending_user_id,
                is_active=True,
                is_staff=True,
                is_superuser=True,
            )
            .first()
            if pending_user_id
            else None
        )
        if pending_user is not None:
            form = AdminPinForm(request.POST or None)
            if request.method == "POST":
                if form.is_valid() and verify_admin_pin(pending_user, form.cleaned_data["pin"]):
                    set_gate(request, pending_user, next_url)
                    return redirect("admin:login")
                if form.is_valid():
                    register_gate_failure(request)
                    form.add_error(None, "That PIN could not be verified.")
                if admin_gate_locked(request):
                    form.add_error(None, "Too many attempts. Try again in 15 minutes.")
            return self._render_admin_page(
                request,
                "admin/access.html",
                {
                    "title": "Administration access",
                    "site_title": self.site_title,
                    "form": form,
                    "pin_step": True,
                    "next": next_url,
                },
            )

        form = AdminGateIdentifierForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            admin_user = resolve_admin_identifier(form.cleaned_data["identifier"])
            if admin_user is None:
                form.add_error(None, "We could not verify that administration account.")
            elif pin_is_enabled(admin_user):
                request.session[ADMIN_GATE_PENDING_PIN] = str(admin_user.pk)
                request.session["gccad_gate_next"] = next_url
                request.session.modified = True
                return redirect(self._access_url(next_url))
            else:
                set_gate(request, admin_user, next_url)
                return redirect("admin:login")

        return self._render_admin_page(
            request,
            "admin/access.html",
            {
                "title": "Administration access",
                "site_title": self.site_title,
                "form": form,
                "next": next_url,
            },
        )

    def otp(self, request):
        user = pending_otp_user(request)
        if user is None or not gate_is_valid(request, user):
            clear_otp_challenge(request)
            return redirect(self._access_url(request.get_full_path()))
        device = confirmed_totp_device(user)
        if device is None:
            clear_otp_challenge(request)
            return redirect("admin:login")

        form = AdminOtpForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            if device.verify_token(form.cleaned_data["token"]):
                next_url = pending_otp_next(request)
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                mark_otp_verified(request, user, device)
                clear_otp_challenge(request)
                return redirect(next_url)
            locked = register_otp_failure(request)
            form.add_error(None, "That authenticator code could not be verified.")
            if locked:
                clear_otp_challenge(request)
                clear_gate(request)
                form.add_error(None, "Too many attempts. Start again from the private admin URL.")

        return self._render_admin_page(
            request,
            "admin/otp.html",
            {
                "title": "Authenticator verification",
                "site_title": self.site_title,
                "form": form,
                "username": user.get_username(),
            },
        )

    def recovery(self, request):
        if request.user.is_authenticated and not self.has_permission(request):
            return HttpResponseForbidden("Administration access is restricted.")
        form = AdminRecoveryRequestForm(request.POST or None)
        if recovery_is_locked(request):
            return self._render_admin_page(
                request,
                "admin/recovery.html",
                {
                    "title": "Recover administration access",
                    "site_title": self.site_title,
                    "form": form,
                    "locked": True,
                },
                status=429,
            )
        if request.method == "POST" and form.is_valid():
            email = form.cleaned_data["email"].strip()
            admin_user = get_user_model().objects.filter(
                email__iexact=email,
                is_active=True,
                is_staff=True,
                is_superuser=True,
            ).first()
            if admin_user is not None and admin_user.email:
                create_admin_recovery_token(request, admin_user)
            else:
                register_recovery_failure(request)
            if recovery_is_locked(request):
                return self._render_admin_page(
                    request,
                    "admin/recovery.html",
                    {
                        "title": "Recover administration access",
                        "site_title": self.site_title,
                        "form": form,
                        "locked": True,
                    },
                    status=429,
                )
            return self._render_admin_page(
                request,
                "admin/recovery_sent.html",
                {"title": "Check your email", "site_title": self.site_title},
            )
        return self._render_admin_page(
            request,
            "admin/recovery.html",
            {
                "title": "Recover administration access",
                "site_title": self.site_title,
                "form": form,
            },
        )

    def recovery_confirm(self, request, token):
        recovery_token = find_admin_recovery_token(token)
        if recovery_token is None:
            return self._render_admin_page(
                request,
                "admin/recovery_invalid.html",
                {"title": "Recovery link unavailable", "site_title": self.site_title},
                status=410,
            )
        form = AdminRecoveryResetForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            recovery_token = consume_admin_recovery_token(token)
            if recovery_token is None:
                return self._render_admin_page(
                    request,
                    "admin/recovery_invalid.html",
                    {"title": "Recovery link unavailable", "site_title": self.site_title},
                    status=410,
                )
            reset_admin_security(recovery_token.user, form.cleaned_data["new_pin"])
            revoke_user_sessions(recovery_token.user)
            clear_admin_challenges(request)
            return self._render_admin_page(
                request,
                "admin/recovery_complete.html",
                {"title": "Security reset complete", "site_title": self.site_title},
            )
        return self._render_admin_page(
            request,
            "admin/recovery_confirm.html",
            {
                "title": "Reset administration security",
                "site_title": self.site_title,
                "form": form,
            },
        )

    def security_settings(self, request):
        profile = admin_security_profile(request.user)
        confirmed_device = confirmed_totp_device(request.user)
        pending_device_id = request.session.get(ADMIN_OTP_ENROLLMENT_DEVICE)
        pending_device = (
            TOTPDevice.objects.filter(
                user=request.user,
                pk=pending_device_id,
                confirmed=False,
            ).first()
            if pending_device_id
            else None
        )
        pin_form = AdminPinSettingsForm(
            request.POST if request.POST.get("action") == "save-pin" else None,
            profile=profile,
        )
        two_factor_form = AdminTwoFactorStartForm(
            request.POST if request.POST.get("action") in {"begin-2fa", "disable-2fa"} else None,
        )

        if request.method == "POST":
            action = request.POST.get("action")
            if action == "save-pin":
                if pin_form.is_valid():
                    profile.pin_enabled = pin_form.cleaned_data["pin_enabled"]
                    profile.pin_hash = (
                        make_password(pin_form.cleaned_data["new_pin"])
                        if profile.pin_enabled and pin_form.cleaned_data["new_pin"]
                        else profile.pin_hash if profile.pin_enabled else ""
                    )
                    profile.save(update_fields=["pin_enabled", "pin_hash", "updated_at"])
                    messages.success(request, "Admin PIN settings saved.")
                    return redirect("admin:security")
            elif action in {"begin-2fa", "disable-2fa"}:
                if two_factor_form.is_valid():
                    if action == "disable-2fa":
                        remove_totp_devices(request.user)
                        request.session.pop(ADMIN_OTP_ENROLLMENT_DEVICE, None)
                        request.session.pop("gccad_otp_verified_user", None)
                        messages.success(request, "Authenticator 2FA has been disabled.")
                        return redirect("admin:security")
                    else:
                        pending_device = begin_totp_enrollment(request.user)
                        request.session[ADMIN_OTP_ENROLLMENT_DEVICE] = pending_device.pk
                        request.session.modified = True
                        messages.info(request, "Scan the QR code, then choose the enable button to finish authenticator setup.")
                        return redirect("admin:security")
            elif action == "confirm-2fa" and pending_device is not None:
                pending_device.confirmed = True
                pending_device.save(update_fields=["confirmed"])
                mark_otp_verified(request, request.user, pending_device)
                request.session.pop(ADMIN_OTP_ENROLLMENT_DEVICE, None)
                request.session.modified = True
                messages.success(request, "Authenticator 2FA is now enabled.")
                return redirect("admin:security")
            elif action == "cancel-2fa":
                if pending_device is not None:
                    pending_device.delete()
                request.session.pop(ADMIN_OTP_ENROLLMENT_DEVICE, None)
                request.session.modified = True
                return redirect("admin:security")

        context = {
            **self.each_context(request),
            "title": "Security settings",
            "subtitle": "Private administration",
            "profile": profile,
            "two_factor_enabled": confirmed_device is not None,
            "pending_device": pending_device,
            "pending_qr": totp_qr_data_uri(pending_device) if pending_device else "",
            "pin_form": pin_form,
            "two_factor_form": two_factor_form,
        }
        request.current_app = self.name
        return self._render_admin_page(request, "admin/security.html", context)
