"""Database-backed fixed-window API rate limiting."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps

from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone

from .models import APIRateLimitBucket
from .security import client_ip


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime


def _identity(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return f"user:{user.pk}"
    return f"ip:{client_ip(request) or 'unknown'}"


def _settings_values():
    return (
        max(1, int(settings.GCC_API_RATE_LIMIT)),
        max(1, int(settings.GCC_API_RATE_WINDOW_SECONDS)),
    )


def _get_or_create_locked_bucket(identity, now):
    try:
        return APIRateLimitBucket.objects.select_for_update().get(identity=identity)
    except APIRateLimitBucket.DoesNotExist:
        try:
            return APIRateLimitBucket.objects.create(
                identity=identity,
                window_started_at=now,
            )
        except IntegrityError:
            return APIRateLimitBucket.objects.select_for_update().get(identity=identity)


def consume_api_rate_limit(request):
    """Consume one request slot and return the decision plus reset metadata."""

    limit, window_seconds = _settings_values()
    now = timezone.now()
    window = timedelta(seconds=window_seconds)

    with transaction.atomic():
        bucket = _get_or_create_locked_bucket(_identity(request), now)
        if now >= bucket.window_started_at + window:
            bucket.window_started_at = now
            bucket.request_count = 0

        reset_at = bucket.window_started_at + window
        if bucket.request_count >= limit:
            return RateLimitDecision(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_at=reset_at,
            )

        bucket.request_count += 1
        bucket.save(update_fields=["window_started_at", "request_count", "updated_at"])
        return RateLimitDecision(
            allowed=True,
            limit=limit,
            remaining=limit - bucket.request_count,
            reset_at=reset_at,
        )


def _retry_after(decision):
    return max(1, math.ceil((decision.reset_at - timezone.now()).total_seconds()))


def _add_rate_limit_headers(response, decision):
    response["X-RateLimit-Limit"] = str(decision.limit)
    response["X-RateLimit-Remaining"] = str(decision.remaining)
    response["X-RateLimit-Reset"] = str(int(decision.reset_at.timestamp()))
    response["X-RateLimit-Policy"] = f"{decision.limit};w={int(settings.GCC_API_RATE_WINDOW_SECONDS)}"
    return response


def _rate_limited_response(decision):
    retry_after = _retry_after(decision)
    response = JsonResponse(
        {
            "error": "Rate limit exceeded.",
            "retry_after": retry_after,
        },
        status=429,
    )
    response["Retry-After"] = str(retry_after)
    return _add_rate_limit_headers(response, decision)


def api_rate_limit(view):
    """Apply the API limiter and expose standard response headers."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            decision = consume_api_rate_limit(request)
        except DatabaseError:
            logger.exception("API rate-limit storage is unavailable.")
            return JsonResponse(
                {"error": "API rate limiting is temporarily unavailable."},
                status=503,
            )

        if not decision.allowed:
            return _rate_limited_response(decision)

        response = view(request, *args, **kwargs)
        return _add_rate_limit_headers(response, decision)

    return wrapped
