from __future__ import annotations

import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_ERROR_MESSAGE = "Complete the security check and try again."
MOBILE_WEBVIEW_USER_AGENT_MARKER = "GrandCoastMobile/"
MOBILE_WEBVIEW_HEADER = "HTTP_X_GRAND_COAST_MOBILE"


def is_mobile_webview(request):
    if request is None:
        return False
    if request.META.get(MOBILE_WEBVIEW_HEADER) == "1":
        return True
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return MOBILE_WEBVIEW_USER_AGENT_MARKER in user_agent


def get_turnstile_site_key(request=None):
    if is_mobile_webview(request):
        return ""
    site_key = getattr(settings, "CLOUDFLARE_TURNSTILE_SITE_KEY", "") or ""
    secret_key = getattr(settings, "CLOUDFLARE_TURNSTILE_SECRET_KEY", "") or ""
    return site_key if site_key and secret_key else ""


def verify_turnstile_request(request, expected_action=None):
    """
    Validate the single-use Turnstile token submitted by a website form.

    Native mobile requests are intentionally exempt because the mobile app
    does not present the website's anti-bot challenge. An unset key pair also
    leaves local development usable until Turnstile is configured.
    """
    if request is None or is_mobile_webview(request):
        return True

    site_key = get_turnstile_site_key(request)
    secret_key = getattr(settings, "CLOUDFLARE_TURNSTILE_SECRET_KEY", "") or ""
    if not site_key or not secret_key:
        return True

    token = request.POST.get("cf-turnstile-response", "").strip()
    if not token:
        return False

    payload = {
        "secret": secret_key,
        "response": token,
    }
    remote_ip = request.META.get("REMOTE_ADDR")
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        verification_request = Request(
            TURNSTILE_VERIFY_URL,
            data=urlencode(payload).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(verification_request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (OSError, TypeError, ValueError, URLError):
        return False

    if not isinstance(result, dict) or not result.get("success"):
        return False

    returned_action = result.get("action")
    if expected_action and returned_action and returned_action != expected_action:
        return False

    return True
