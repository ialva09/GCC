"""Certification probes for the protected storage boundary.

The lifecycle simulation creates real model files. These probes verify that
the configured S3-compatible backend can round-trip a disposable object,
unsigned object access is not public, and Django's protected delivery routes
still enforce object and project scope.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client as DjangoClient
from django.urls import reverse

from .models import Project


def _check(checks, name, condition, detail=""):
    if not condition:
        raise AssertionError(f"Certification check failed: {name}. {detail}".strip())
    checks.append({"name": name, "passed": True, "detail": str(detail or "")})


def _unsigned_url(value):
    parts = urlsplit(str(value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _unsigned_status(url):
    request = Request(url, method="GET", headers={"User-Agent": "grand-coast-certification"})
    try:
        with urlopen(request, timeout=8) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)
    except URLError as exc:
        raise AssertionError(f"Unable to verify private object access: {exc}") from exc


def safe_error(value):
    result = str(value)
    for secret_name in (
        "SUPABASE_S3_ACCESS_KEY",
        "SUPABASE_S3_SECRET_KEY",
        "DJANGO_SECRET_KEY",
        "EXPO_ACCESS_TOKEN",
    ):
        secret = str(os.environ.get(secret_name) or "")
        if secret:
            result = result.replace(secret, "[redacted]")
    return re.sub(r"(?i)(secret|token|password|api_key)=([^&\s]+)", r"\1=[redacted]", result)


def _create_boundary_project(result):
    """Create an unrelated project used only for authorization assertions."""

    owner = get_user_model().objects.get(pk=result["pilot"]["user_ids"]["owner"])
    return Project.objects.create(
        title="Certification Boundary Project",
        location="Santa Barbara, CA",
        project_type="renovation",
        project_code=f"CERT-{uuid.uuid4().hex[:10].upper()}",
        summary="Unrelated disposable project for authorization checks.",
        is_published=False,
        created_by=owner,
    )


def _protected_delivery_checks(result, checks, boundary_project):
    users = result["pilot"]["user_ids"]
    document_id = result["records"]["document_id"]
    summary_url = reverse("operations-api:project-summary", kwargs={"pk": boundary_project.pk})
    document_url = reverse("operations:document-file", kwargs={"pk": document_id})

    owner = DjangoClient()
    owner.force_login(get_user_model().objects.get(pk=users["owner"]))
    _check(checks, "authorized protected document delivery", owner.get(document_url).status_code == 200)
    _check(
        checks,
        "owner can see the unrelated certification project",
        owner.get(summary_url).status_code == 200,
    )

    field = DjangoClient()
    field.force_login(get_user_model().objects.get(pk=users["field"]))
    _check(
        checks,
        "field user cannot cross project boundary",
        field.get(summary_url).status_code in {403, 404},
    )

    client = DjangoClient()
    client.force_login(get_user_model().objects.get(pk=users["client"]))
    _check(
        checks,
        "client cannot cross project boundary",
        client.get(summary_url).status_code in {403, 404},
    )
    _check(
        checks,
        "client cannot download unrelated internal document",
        client.get(document_url).status_code in {403, 404},
    )


def run_storage_certification(result, *, storage_mode):
    """Run checks against the currently configured storage backend."""

    if storage_mode not in {"emulator", "provider"}:
        raise AssertionError(
            "Storage certification accepts one configured target at a time; use the PowerShell launcher for Both."
        )
    if not getattr(settings, "GCC_STORAGE_SMOKE_ENABLED", False):
        raise AssertionError("Set GCC_STORAGE_SMOKE_ENABLED=true for storage certification.")
    if not getattr(settings, "USE_SUPABASE_STORAGE", False):
        raise AssertionError(
            "Storage certification requires USE_SUPABASE_STORAGE=true so the S3-compatible backend is exercised."
        )

    checks = []
    boundary_project = _create_boundary_project(result)
    probe_name = f"certification-probe-{uuid.uuid4().hex}.txt"
    payload = b"Grand Coast disposable private-storage certification."
    saved_name = None
    try:
        saved_name = default_storage.save(probe_name, ContentFile(payload))
        _check(checks, "storage write succeeds", bool(saved_name))
        _check(checks, "storage object exists", default_storage.exists(saved_name))
        with default_storage.open(saved_name, "rb") as opened:
            _check(checks, "storage read round-trip succeeds", opened.read() == payload)

        signed_url = default_storage.url(saved_name)
        _check(checks, "private storage returns a signed delivery URL", "?" in str(signed_url))
        unsigned_status = _unsigned_status(_unsigned_url(signed_url))
        _check(
            checks,
            "unsigned object access is denied",
            unsigned_status in {401, 403, 404},
            f"received HTTP {unsigned_status}",
        )
        _protected_delivery_checks(result, checks, boundary_project)
    finally:
        if saved_name:
            default_storage.delete(saved_name)

    return {
        "passed": True,
        "storage_mode": storage_mode,
        "checks": checks,
        "boundary_project_id": str(boundary_project.pk),
        "object_name": str(saved_name or ""),
        "storage_prefix": str(getattr(settings, "GCC_STORAGE_PREFIX", "")),
    }


def cleanup_storage_prefix():
    """Delete only the current certification prefix from an S3-compatible bucket."""

    prefix = str(getattr(settings, "GCC_STORAGE_PREFIX", "") or "").strip("/")
    if not prefix or not getattr(settings, "USE_SUPABASE_STORAGE", False):
        return {"deleted": 0, "skipped": True}
    storage = default_storage
    bucket = getattr(storage, "bucket", None)
    if bucket is None:
        return {"deleted": 0, "skipped": True}
    deleted = bucket.objects.filter(Prefix=f"{prefix}/").delete()
    return {"deleted": int(deleted.get("Deleted", 0)), "skipped": False}


def ensure_storage_bucket(*, create_if_missing=False):
    """Verify the configured bucket, optionally creating an emulator bucket."""

    if not getattr(settings, "USE_SUPABASE_STORAGE", False):
        raise AssertionError("USE_SUPABASE_STORAGE=true is required.")
    storage = default_storage
    bucket = getattr(storage, "bucket", None)
    if bucket is None:
        raise AssertionError("The configured storage backend does not expose an S3 bucket.")
    client = bucket.meta.client
    try:
        client.head_bucket(Bucket=bucket.name)
    except Exception as exc:
        if not create_if_missing:
            raise AssertionError(f"Configured storage bucket is unavailable: {safe_error(exc)}") from exc
        try:
            region = str(getattr(settings, "SUPABASE_S3_REGION", "") or "")
            kwargs = {"Bucket": bucket.name}
            if region and region != "us-east-1":
                kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
            client.create_bucket(**kwargs)
            client.head_bucket(Bucket=bucket.name)
        except Exception as create_exc:
            raise AssertionError(f"Unable to create the disposable emulator bucket: {safe_error(create_exc)}") from create_exc
    return {"bucket": bucket.name, "endpoint": str(getattr(settings, "SUPABASE_STORAGE_OPTIONS", {}).get("endpoint_url") or "")}


def sanitized_json(value):
    """Return JSON-safe data while excluding credentials and secret-like values."""

    def scrub(item):
        if isinstance(item, dict):
            return {
                key: scrub(value)
                for key, value in item.items()
                if key.lower() not in {"credentials", "password", "token", "secret", "api_key"}
            }
        if isinstance(item, list):
            return [scrub(value) for value in item]
        return item

    return json.loads(json.dumps(scrub(value), default=str))
