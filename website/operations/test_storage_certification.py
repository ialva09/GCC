from __future__ import annotations

import os
from unittest.mock import patch

from django.test import SimpleTestCase

from .storage_certification import sanitized_json, safe_error


class StorageCertificationHelperTests(SimpleTestCase):
    def test_sanitized_report_removes_credentials_and_secret_fields(self):
        result = sanitized_json(
            {
                "passed": True,
                "credentials": {"owner": {"username": "sim-owner", "password": "secret"}},
                "storage": {
                    "token": "one-time-token",
                    "secret": "provider-secret",
                    "object_name": "certification/run/file.txt",
                },
            }
        )

        self.assertNotIn("credentials", result)
        self.assertNotIn("token", result["storage"])
        self.assertNotIn("secret", result["storage"])
        self.assertEqual(result["storage"]["object_name"], "certification/run/file.txt")

    def test_safe_error_redacts_configured_storage_secrets(self):
        with patch.dict(
            os.environ,
            {
                "SUPABASE_S3_ACCESS_KEY": "cert-access",
                "SUPABASE_S3_SECRET_KEY": "cert-secret",
            },
            clear=False,
        ):
            # safe_error reads process environment for values that could be
            # echoed by a provider exception; the generic key/value scrub
            # still protects provider-shaped error strings.
            message = safe_error(
                "endpoint failed with cert-access cert-secret secret=cert-secret token=temporary-token"
            )

        self.assertNotIn("cert-access", message)
        self.assertNotIn("cert-secret", message)
        self.assertNotIn("temporary-token", message)
