from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import Activity, Client, ClientInvite, EmployeeInvite, EmployeeProfile, Estimate, Lead


ROLE_NAMES = ("Owner", "Manager", "Office", "Field")


def record_activity(message, detail="", *, actor=None, lead=None, estimate=None, project=None):
    return Activity.objects.create(
        message=message,
        detail=detail,
        actor=actor,
        lead=lead,
        estimate=estimate,
        project=project,
    )


def get_or_create_client_for_lead(lead, *, actor=None):
    client = lead.client
    if client is None:
        client = Client.objects.filter(email__iexact=lead.email).first()
    if client is None:
        client = Client.objects.create(
            name=lead.name,
            email=lead.email,
            phone=lead.phone,
        )
    else:
        changed = []
        if not client.name and lead.name:
            client.name = lead.name
            changed.append("name")
        if not client.phone and lead.phone:
            client.phone = lead.phone
            changed.append("phone")
        if changed:
            client.save(update_fields=changed + ["updated_at"])
    if lead.client_id != client.id:
        lead.client = client
        lead.save(update_fields=["client", "updated_at"])
    return client


@transaction.atomic
def create_client_invite(client, *, actor=None):
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    ClientInvite.objects.filter(client=client, accepted_at__isnull=True, expires_at__gt=timezone.now()).update(
        expires_at=timezone.now()
    )
    invite = ClientInvite.objects.create(
        client=client,
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(days=7),
        created_by=actor,
    )
    return invite, raw_token


def find_invite(raw_token):
    if not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    invite = ClientInvite.objects.select_related("client").filter(token_hash=token_hash).first()
    return invite if invite and invite.is_usable else None


def complete_client_invite(invite, form):
    user_model = get_user_model()
    with transaction.atomic():
        invite = ClientInvite.objects.select_for_update().select_related("client").get(pk=invite.pk)
        if not invite.is_usable:
            raise ValidationError("This invite link has expired or has already been used.")
        if invite.client.user_id:
            raise ValidationError("This client already has portal access.")
        user = user_model.objects.create_user(
            username=form.cleaned_data["username"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            password=form.cleaned_data["password1"],
            email=invite.client.email,
        )
        invite.client.user = user
        invite.client.save(update_fields=["user", "updated_at"])
        invite.accepted_at = timezone.now()
        invite.save(update_fields=["accepted_at"])
    return user


def client_portal_url(client_id=None):
    url = reverse("operations:portal")
    return f"{url}?client={client_id}" if client_id else url


def estimate_total(estimate):
    return estimate.total


def ensure_role_groups():
    "Create the four application roles without replacing existing group membership."
    groups = {name: Group.objects.get_or_create(name=name)[0] for name in ROLE_NAMES}
    operation_permissions = Permission.objects.filter(content_type__app_label="operations")
    auth_permissions = Permission.objects.filter(
        content_type__app_label="auth",
        content_type__model__in={"user", "group"},
    )
    groups["Owner"].permissions.set(operation_permissions | auth_permissions)
    groups["Manager"].permissions.set(operation_permissions)
    office_codenames = {
        "view_client", "add_client", "change_client", "view_lead", "add_lead", "change_lead",
        "view_task", "add_task", "change_task", "view_estimate", "add_estimate", "change_estimate",
        "view_estimatelineitem", "add_estimatelineitem", "change_estimatelineitem", "view_project",
        "change_project", "view_milestone", "change_milestone", "view_projectupdate", "add_projectupdate",
        "change_projectupdate", "view_projectdocument", "add_projectdocument", "change_projectdocument",
        "view_clientmessage", "add_clientmessage", "change_clientmessage", "view_mediaasset", "change_mediaasset",
        "view_scheduleevent", "view_timeentry", "view_employeeprofile", "view_service", "view_processstep",
        "view_sitesettings",
    }
    groups["Office"].permissions.set(operation_permissions.filter(codename__in=office_codenames))
    field_codenames = {
        "view_project", "view_milestone", "view_projectupdate", "add_projectupdate", "change_projectupdate",
        "view_task", "change_task", "view_mediaasset", "add_mediaasset", "change_mediaasset",
        "view_scheduleevent", "view_timeentry", "add_timeentry", "change_timeentry", "view_client",
    }
    groups["Field"].permissions.set(operation_permissions.filter(codename__in=field_codenames))
    return groups


@transaction.atomic
def create_employee_invite(*, email, first_name="", last_name="", group, actor=None, employee=None, purpose=EmployeeInvite.Purpose.ONBOARDING):
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    EmployeeInvite.objects.filter(
        email__iexact=email,
        accepted_at__isnull=True,
        expires_at__gt=timezone.now(),
        purpose=purpose,
    ).update(expires_at=timezone.now())
    lifetime = timedelta(days=7 if purpose == EmployeeInvite.Purpose.ONBOARDING else 1)
    invite = EmployeeInvite.objects.create(
        employee=employee,
        email=email,
        first_name=first_name,
        last_name=last_name,
        group=group,
        purpose=purpose,
        token_hash=token_hash,
        expires_at=timezone.now() + lifetime,
        created_by=actor,
    )
    return invite, raw_token


def find_employee_invite(raw_token):
    if not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    invite = EmployeeInvite.objects.select_related("employee__user", "group").filter(token_hash=token_hash).first()
    return invite if invite and invite.is_usable else None


@transaction.atomic
def complete_employee_invite(invite, form):
    user_model = get_user_model()
    with transaction.atomic():
        invite = EmployeeInvite.objects.select_for_update().select_related("employee__user", "group").get(pk=invite.pk)
        if not invite.is_usable:
            raise ValidationError("This employee link has expired or has already been used.")
        if invite.purpose == EmployeeInvite.Purpose.PASSWORD_RESET:
            if not invite.employee_id or not invite.employee.user_id:
                raise ValidationError("This password reset link is no longer valid.")
            user = invite.employee.user
            user.set_password(form.cleaned_data["password1"])
            user.save(update_fields=["password"])
        else:
            user = user_model.objects.create_user(
                username=form.cleaned_data["username"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=invite.email,
                password=form.cleaned_data["password1"],
                is_staff=True,
            )
            user.groups.add(invite.group)
            profile = EmployeeProfile.objects.create(user=user)
            invite.employee = profile
            invite.save(update_fields=["employee"])
        invite.accepted_at = timezone.now()
        invite.save(update_fields=["accepted_at"])
    return user
