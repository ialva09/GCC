from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_health_check_returns_healthy_json(self):
        response = self.client.get(reverse("operations-api:health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy", "database": "connected"})

    def test_health_check_returns_service_unavailable_when_database_is_down(self):
        with patch("operations.health.connection.cursor", side_effect=DatabaseError("database unavailable")):
            response = self.client.get(reverse("operations-api:health"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unhealthy", "database": "unavailable"})

    def test_health_check_only_accepts_get(self):
        response = self.client.post(reverse("operations-api:health"))

        self.assertEqual(response.status_code, 405)
