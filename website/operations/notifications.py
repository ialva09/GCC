"""Persistent employee/client notifications and Expo Push Service delivery."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ClientNotification, EmployeeNotification, MobilePushDevice, PushDelivery


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
    exclude_users=None,
    lead=None,
    estimate=None,
    project=None,
    task=None,
    message=None,
):
    """Create inbox rows in the current transaction and dispatch after commit."""
    employee_ids = []
    seen = set()
    excluded_ids = {
        getattr(employee, "pk", employee)
        for employee in (exclude_users or [])
    }
    for employee in employees:
        employee_id = getattr(employee, "pk", employee)
        if employee_id in seen or employee_id in excluded_ids:
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
            lead_id=getattr(lead, "pk", lead),
            estimate_id=getattr(estimate, "pk", estimate),
            project_id=getattr(project, "pk", project),
            task_id=getattr(task, "pk", task),
            message_id=getattr(message, "pk", message),
        )
        for employee_id in employee_ids
    ]
    notifications = EmployeeNotification.objects.bulk_create(notifications)
    notification_ids = [notification.pk for notification in notifications]
    transaction.on_commit(
        lambda notification_ids=notification_ids: dispatch_notification_ids(notification_ids)
    )
    return notifications


def queue_client_notifications(
    clients,
    *,
    kind,
    title,
    body,
    destination_url="",
    metadata=None,
    created_by=None,
    exclude_clients=None,
    lead=None,
    estimate=None,
    project=None,
    task=None,
    message=None,
):
    """Create durable client alerts after the triggering write succeeds."""
    client_ids = []
    seen = set()
    excluded_ids = {
        getattr(client, "pk", client)
        for client in (exclude_clients or [])
    }
    for client in clients:
        client_id = getattr(client, "pk", client)
        if not client_id or client_id in seen or client_id in excluded_ids:
            continue
        seen.add(client_id)
        client_ids.append(client_id)

    if not client_ids:
        return []

    notifications = ClientNotification.objects.bulk_create(
        [
            ClientNotification(
                client_id=client_id,
                kind=kind,
                title=title,
                body=body,
                destination_url=destination_url,
                metadata=metadata or {},
                created_by=created_by,
                lead_id=getattr(lead, "pk", lead),
                estimate_id=getattr(estimate, "pk", estimate),
                project_id=getattr(project, "pk", project),
                task_id=getattr(task, "pk", task),
                message_id=getattr(message, "pk", message),
            )
            for client_id in client_ids
        ]
    )
    notification_ids = [notification.pk for notification in notifications]
    transaction.on_commit(
        lambda notification_ids=notification_ids: dispatch_client_notification_ids(notification_ids)
    )
    return notifications


def _client_push_destination(notification):
    """Return a portal-only destination suitable for a client device."""
    parsed = urlsplit(str(notification.destination_url or ""))
    path = parsed.path or ""
    if path in {"/portal", "/portal/"}:
        return "/portal/notifications/"
    if parsed.scheme or parsed.netloc or not path.startswith("/portal/"):
        return "/portal/notifications/"
    return urlunsplit(("", "", path, parsed.query, ""))


def _delivery_notification(delivery):
    return delivery.notification or delivery.client_notification


def _delivery_payload(notification, device):
    if isinstance(notification, ClientNotification):
        # Client pushes intentionally carry no arbitrary metadata.  The portal
        # inbox remains the source of detail and the mobile client is only
        # given a safe internal destination plus the durable alert identity.
        destination_url = _client_push_destination(notification)
        data = {}
    else:
        destination_url = notification.destination_url
        data = dict(notification.metadata or {})
    data.update(
        {
            "url": destination_url,
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
    notification = _delivery_notification(delivery)
    if notification is None:
        _mark_delivery(
            delivery,
            status=PushDelivery.Status.INVALID,
            detail="The delivery has no notification.",
        )
        return delivery

    if not delivery.device_id or not delivery.device or not delivery.device.is_active:
        _mark_delivery(delivery, status=PushDelivery.Status.INVALID, detail="The device is inactive.")
        return delivery

    if isinstance(notification, ClientNotification):
        device_matches = (
            delivery.device.client_id == notification.client_id
            and delivery.device.employee_id is None
        )
    else:
        device_matches = (
            delivery.device.employee_id == notification.employee_id
            and delivery.device.client_id is None
        )
    if not device_matches:
        _mark_delivery(
            delivery,
            status=PushDelivery.Status.INVALID,
            detail="The device is not owned by the notification recipient.",
        )
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
        data=json.dumps(_delivery_payload(notification, delivery.device)).encode("utf-8"),
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


def _dispatch_notification_batch(notifications, *, owner_field, delivery_field):
    for notification in notifications:
        owner = getattr(notification, owner_field)
        devices = [device for device in owner.mobile_push_devices.all() if device.is_active]
        for device in devices:
            delivery, _ = PushDelivery.objects.get_or_create(device=device, **{delivery_field: notification})
            if delivery.status in {PushDelivery.Status.SENT, PushDelivery.Status.INVALID}:
                continue
            if delivery.attempt_count >= MAX_PUSH_ATTEMPTS:
                continue
            if _push_enabled():
                deliver_push_delivery(delivery)


def dispatch_notification_ids(notification_ids):
    """Create one delivery row per active employee device and attempt pushes."""
    notifications = EmployeeNotification.objects.filter(pk__in=notification_ids).prefetch_related(
        "employee__mobile_push_devices"
    )
    _dispatch_notification_batch(
        notifications,
        owner_field="employee",
        delivery_field="notification",
    )


def dispatch_client_notification_ids(notification_ids):
    """Create one delivery row per active client device and attempt pushes."""
    notifications = ClientNotification.objects.filter(pk__in=notification_ids).prefetch_related(
        "client__mobile_push_devices"
    )
    _dispatch_notification_batch(
        notifications,
        owner_field="client",
        delivery_field="client_notification",
    )


def retry_pending_push_deliveries(*, limit=100):
    if not _push_enabled():
        return 0
    deliveries = PushDelivery.objects.filter(
        status=PushDelivery.Status.PENDING,
        attempt_count__lt=MAX_PUSH_ATTEMPTS,
    ).select_related("notification", "client_notification", "device", "device__employee", "device__client")[:limit]
    count = 0
    for delivery in deliveries:
        deliver_push_delivery(delivery)
        count += 1
    failed_deliveries = PushDelivery.objects.filter(
        status=PushDelivery.Status.FAILED,
        attempt_count__lt=MAX_PUSH_ATTEMPTS,
    ).select_related("notification", "client_notification", "device", "device__employee", "device__client")[: max(0, limit - count)]
    for delivery in failed_deliveries:
        deliver_push_delivery(delivery)
        count += 1
    return count
