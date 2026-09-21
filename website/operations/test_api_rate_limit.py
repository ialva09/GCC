from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from .api_rate_limit import consume_api_rate_limit


@override_settings(GCC_API_RATE_LIMIT=2, GCC_API_RATE_WINDOW_SECONDS=60)
class APIRateLimitTests(TestCase):
    def test_fixed_window_allows_limit_then_denies_next_request(self):
        request = RequestFactory().get(
            "/api/v1/me/",
            REMOTE_ADDR="198.51.100.20",
        )
        request.user = AnonymousUser()

        first = consume_api_rate_limit(request)
        second = consume_api_rate_limit(request)
        third = consume_api_rate_limit(request)

        self.assertTrue(first.allowed)
        self.assertEqual(first.remaining, 1)
        self.assertTrue(second.allowed)
        self.assertEqual(second.remaining, 0)
        self.assertFalse(third.allowed)
        self.assertEqual(third.remaining, 0)

    def test_api_endpoint_returns_429_and_rate_limit_headers(self):
        response = self.client.get(
            reverse("operations-api:me"),
            REMOTE_ADDR="198.51.100.21",
        )
        limited = self.client.get(
            reverse("operations-api:me"),
            REMOTE_ADDR="198.51.100.21",
        )
        exhausted = self.client.get(
            reverse("operations-api:me"),
            REMOTE_ADDR="198.51.100.21",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(limited.status_code, 401)
        self.assertEqual(exhausted.status_code, 429)
        self.assertEqual(exhausted.json()["error"], "Rate limit exceeded.")
        self.assertEqual(exhausted["X-RateLimit-Limit"], "2")
        self.assertEqual(exhausted["X-RateLimit-Remaining"], "0")
        self.assertTrue(int(exhausted["Retry-After"]) >= 1)

    def test_authenticated_requests_are_bucketed_by_user(self):
        user = self._create_user()
        self.client.force_login(user)

        first = self.client.get(
            reverse("operations-api:me"),
            REMOTE_ADDR="198.51.100.22",
        )
        second = self.client.get(
            reverse("operations-api:me"),
            REMOTE_ADDR="198.51.100.23",
        )
        third = self.client.get(
            reverse("operations-api:me"),
            REMOTE_ADDR="198.51.100.24",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)

    def _create_user(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.create_user(
            username="rate-limit-user",
            password="rate-limit-password",
            is_staff=True,
            is_superuser=True,
        )
