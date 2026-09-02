"""Persistent employee notifications and Expo Push Service delivery."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import EmployeeNotification, MobilePushDevice, PushDelivery


EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
MAX_PUSH_ATTEMPTS = 5


def _push_enabled():
    return bool(getattr(settings, "EXPO_PUSH_ENABLED", False))


def _push_url():
    return getattr(settings, "EXPO_PUSH_URL", EXPO_PUSH_URL) or EXPO_PUSH_URL


def _push_headers():
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    access_token = getattr(settings, "EXPO_ACCESS_TOKEN", "") or ""
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _is_expo_token(token):
    return str(token or "").startswith(("ExponentPushToken[", "ExpoPushToken["))


def queue_employee_notifications(
    employees,
    *,
    kind,
    title,
    body,
    destination_url="",
    metadata=None,
    created_by=None,
):
    """Create inbox rows in the current transaction and dispatch after commit."""
    employee_ids = []
    seen = set()
    for employee in employees:
        employee_id = getattr(employee, "pk", employee)
        if employee_id in seen:
            continue
        seen.add(employee_id)
        employee_ids.append(employee_id)

    if not employee_ids:
        return []

    notifications = [
        EmployeeNotification(
            employee_id=employee_id,
            kind=kind,
            title=title,
            body=body,
            destination_url=destination_url,
            metadata=metadata or {},
            created_by=created_by,
        )
        for employee_id in employee_ids
    ]
    notifications = EmployeeNotification.objects.bulk_create(notifications)
    notification_ids = [notification.pk for notification in notifications]
    transaction.on_commit(
        lambda notification_ids=notification_ids: dispatch_notification_ids(notification_ids)
    )
    return notifications


def _delivery_payload(notification, device):
    data = dict(notification.metadata or {})
    data.update(
        {
            "url": notification.destination_url,
            "notification_id": str(notification.pk),
            "kind": notification.kind,
        }
    )
    payload = {
        "to": device.token,
        "title": notification.title,
        "body": notification.body,
        "sound": "default",
        "data": data,
    }
    if device.platform.lower() == "android":
        payload["channelId"] = "schedule-updates"
    return payload


def _response_json(response):
    try:
        raw = response.read().decode("utf-8")
        return json.loads(raw or "{}")
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _failure_detail(response_payload, fallback="Expo Push Service did not accept the notification."):
    data = response_payload.get("data") if isinstance(response_payload, dict) else None
    if isinstance(data, dict):
        return str(data.get("message") or data.get("details") or fallback)
    errors = response_payload.get("errors") if isinstance(response_payload, dict) else None
    if errors:
        return "; ".join(str(error.get("message") or error) for error in errors)
    return fallback


def _is_device_not_registered(response_payload):
    serialized = json.dumps(response_payload, sort_keys=True).lower()
    return "devicenotregistered" in serialized or "device not registered" in serialized


def _mark_delivery(delivery, *, status, detail="", ticket_id=""):
    delivery.status = status
    delivery.failure_detail = detail
    if ticket_id:
        delivery.expo_ticket_id = ticket_id
    delivery.last_attempt_at = timezone.now()
    delivery.save(
        update_fields=[
            "status",
            "failure_detail",
            "expo_ticket_id",
            "last_attempt_at",
            "updated_at",
        ]
    )


def deliver_push_delivery(delivery):
    """Attempt one delivery. It is safe to call repeatedly for retryable failures."""
    if not delivery.device_id or not delivery.device or not delivery.device.is_active:
        _mark_delivery(delivery, status=PushDelivery.Status.INVALID, detail="The device is inactive.")
        return delivery

    if not _is_expo_token(delivery.device.token):
        delivery.device.is_active = False
        delivery.device.deactivated_at = timezone.now()
        delivery.device.save(update_fields=["is_active", "deactivated_at", "updated_at"])
        _mark_delivery(delivery, status=PushDelivery.Status.INVALID, detail="The Expo token is invalid.")
        return delivery

    delivery.attempt_count += 1
    delivery.last_attempt_at = timezone.now()
    delivery.save(update_fields=["attempt_count", "last_attempt_at", "updated_at"])

    request = Request(
        _push_url(),
        data=json.dumps(_delivery_payload(delivery.notification, delivery.device)).encode("utf-8"),
        headers=_push_headers(),
        method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            response_payload = _response_json(response)
    except HTTPError as error:
        response_payload = _response_json(error)
        detail = _failure_detail(response_payload, str(error))
        if _is_device_not_registered(response_payload):
            delivery.device.is_active = False
            delivery.device.deactivated_at = timezone.now()
            delivery.device.save(update_fields=["is_active", "deactivated_at", "updated_at"])
            _mark_delivery(delivery, status=PushDelivery.Status.INVALID, detail=detail)
        else:
            _mark_delivery(delivery, status=PushDelivery.Status.FAILED, detail=detail)
        return delivery
    except (TimeoutError, URLError, OSError) as error:
        _mark_delivery(delivery, status=PushDelivery.Status.FAILED, detail=str(error))
        return delivery

    response_data = response_payload.get("data") if isinstance(response_payload, dict) else None
    if isinstance(response_data, list):
        response_data = response_data[0] if response_data else None
    if isinstance(response_data, dict) and response_data.get("status") == "ok":
        _mark_delivery(
            delivery,
            status=PushDelivery.Status.SENT,
            ticket_id=str(response_data.get("id") or ""),
        )
    elif _is_device_not_registered(response_payload):
        delivery.device.is_active = False
        delivery.device.deactivated_at = timezone.now()
        delivery.device.save(update_fields=["is_active", "deactivated_at", "updated_at"])
        _mark_delivery(
            delivery,
            status=PushDelivery.Status.INVALID,
            detail=_failure_detail(response_payload),
        )
    else:
        _mark_delivery(
            delivery,
            status=PushDelivery.Status.FAILED,
            detail=_failure_detail(response_payload),
        )
    return delivery


def dispatch_notification_ids(notification_ids):
    """Create one delivery row per active device and attempt configured pushes."""
    notifications = EmployeeNotification.objects.filter(pk__in=notification_ids).prefetch_related(
        "employee__mobile_push_devices"
    )
    for notification in notifications:
        devices = [device for device in notification.employee.mobile_push_devices.all() if device.is_active]
        for device in devices:
            delivery, _ = PushDelivery.objects.get_or_create(
                notification=notification,
                device=device,
            )
            if delivery.status in {PushDelivery.Status.SENT, PushDelivery.Status.INVALID}:
                continue
            if delivery.attempt_count >= MAX_PUSH_ATTEMPTS:
                continue
            if _push_enabled():
                deliver_push_delivery(delivery)


def retry_pending_push_deliveries(*, limit=100):
    if not _push_enabled():
        return 0
    deliveries = PushDelivery.objects.filter(
        status=PushDelivery.Status.PENDING,
        attempt_count__lt=MAX_PUSH_ATTEMPTS,
    ).select_related("notification", "device")[:limit]
    count = 0
    for delivery in deliveries:
        deliver_push_delivery(delivery)
        count += 1
    failed_deliveries = PushDelivery.objects.filter(
        status=PushDelivery.Status.FAILED,
        attempt_count__lt=MAX_PUSH_ATTEMPTS,
    ).select_related("notification", "device")[: max(0, limit - count)]
    for delivery in failed_deliveries:
        deliver_push_delivery(delivery)
        count += 1
    return count
