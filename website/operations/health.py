"""Public liveness/readiness endpoint for deployment monitors."""

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods


@never_cache
@require_http_methods(['GET', 'HEAD'])
def health_check(request):
    """Return a small JSON response that UptimeRobot can assert against."""

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            database_is_healthy = cursor.fetchone()[0] == 1
    except DatabaseError:
        return JsonResponse(
            {"status": "unhealthy", "database": "unavailable"},
            status=503,
        )

    if not database_is_healthy:
        return JsonResponse(
            {"status": "unhealthy", "database": "unavailable"},
            status=503,
        )

    return JsonResponse({"status": "healthy", "database": "connected"})
