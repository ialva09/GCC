from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from operations.simulation import SIMULATION_PREFIX, run_full_lifecycle
from operations.storage_certification import (
    run_storage_certification,
    safe_error,
    sanitized_json,
)


class Command(BaseCommand):
    help = "Run the disposable Grand Coast lifecycle plus private-storage certification."

    def add_arguments(self, parser):
        parser.add_argument(
            "--storage-mode",
            choices=["emulator", "provider"],
            default="emulator",
            help="Certify the currently configured emulator or provider target. Use run_operations_certification.ps1 for Both.",
        )
        parser.add_argument("--report", help="Write a sanitized JSON report beneath the temporary root.")
        parser.add_argument("--json", action="store_true", help="Print the sanitized report.")

    def _guard(self, report):
        if not getattr(settings, "GCC_SIMULATION_MODE", False):
            raise CommandError("Refusing certification outside GCC_SIMULATION_MODE.")
        if getattr(settings, "GCC_AI_ENABLED", False):
            raise CommandError("Refusing certification while GCC_AI_ENABLED=true.")
        if not getattr(settings, "GCC_EXECUTION_LOOP_ENABLED", False):
            raise CommandError("Set GCC_EXECUTION_LOOP_ENABLED=true for certification.")
        if not getattr(settings, "GCC_STORAGE_SMOKE_ENABLED", False):
            raise CommandError("Set GCC_STORAGE_SMOKE_ENABLED=true for certification.")
        if not getattr(settings, "USE_SUPABASE_STORAGE", False):
            raise CommandError("Set USE_SUPABASE_STORAGE=true for S3-compatible certification.")
        temp_root = Path(tempfile.gettempdir()).resolve()
        database = Path(settings.DATABASES["default"]["NAME"]).expanduser().resolve()
        media_root = Path(settings.MEDIA_ROOT).expanduser().resolve()
        if temp_root not in database.parents or temp_root not in media_root.parents:
            raise CommandError("Certification database and media must be beneath the OS temp folder.")
        if get_user_model().objects.filter(username__startswith=SIMULATION_PREFIX).exists():
            raise CommandError("This certification database already contains sim-* records.")
        if not report:
            return None
        report_path = Path(report).expanduser().resolve()
        if temp_root not in report_path.parents:
            raise CommandError("The certification report must be beneath the OS temp folder.")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        return report_path

    @staticmethod
    def _write_report(path, payload):
        if path:
            path.write_text(json.dumps(sanitized_json(payload), indent=2), encoding="utf-8")

    def handle(self, *args, **options):
        report_path = self._guard(options.get("report"))
        storage_mode = options["storage_mode"]
        payload = {
            "scenario": "development-certification",
            "storage_mode": storage_mode,
            "passed": False,
            "checks": [],
        }
        try:
            lifecycle = run_full_lifecycle()
            storage = run_storage_certification(lifecycle, storage_mode=storage_mode)
            payload.update(
                {
                    "passed": True,
                    "lifecycle": sanitized_json(lifecycle),
                    "storage": sanitized_json(storage),
                    "checks": lifecycle.get("checks", []) + storage.get("checks", []),
                }
            )
        except Exception as exc:
            payload["error"] = safe_error(exc)
            self._write_report(report_path, payload)
            raise CommandError(f"Development certification failed: {safe_error(exc)}") from exc

        self._write_report(report_path, payload)
        self.stdout.write(self.style.SUCCESS("Grand Coast development certification passed."))
        self.stdout.write(f"Project ID: {payload['lifecycle']['pilot']['project_id']}")
        self.stdout.write(f"Storage mode: {storage_mode}")
        self.stdout.write(f"Checks passed: {len(payload['checks'])}")
        if report_path:
            self.stdout.write(f"JSON report: {report_path}")
        if options.get("json"):
            self.stdout.write(json.dumps(sanitized_json(payload), indent=2))
