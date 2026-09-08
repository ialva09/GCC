from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from operations.simulation import SIMULATION_PREFIX, run_full_lifecycle


class Command(BaseCommand):
    help = "Run the disposable Grand Coast full-lifecycle simulation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scenario",
            choices=["full-lifecycle"],
            default="full-lifecycle",
        )
        parser.add_argument(
            "--report",
            help="Write a sanitized JSON report beneath the temporary simulation root.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the sanitized JSON report after the human-readable summary.",
        )

    def _guard(self):
        if not getattr(settings, "GCC_SIMULATION_MODE", False):
            raise CommandError(
                "Refusing to simulate outside GCC_SIMULATION_MODE with isolated paths."
            )
        if getattr(settings, "GCC_AI_ENABLED", False):
            raise CommandError("Refusing to run the simulation while GCC_AI_ENABLED=true.")
        if not getattr(settings, "GCC_EXECUTION_LOOP_ENABLED", False):
            raise CommandError(
                "Set GCC_EXECUTION_LOOP_ENABLED=true for the simulation pilot."
            )
        temp_root = Path(tempfile.gettempdir()).resolve()
        database = Path(settings.DATABASES["default"]["NAME"]).expanduser().resolve()
        media_root = Path(settings.MEDIA_ROOT).expanduser().resolve()
        if temp_root not in database.parents or temp_root not in media_root.parents:
            raise CommandError(
                "Simulation database and media must be beneath the system temporary folder."
            )
        if database.name.lower() in {"db.sqlite3", "database.sqlite3"} and database.parent == temp_root:
            raise CommandError("Simulation database must use a generated disposable subdirectory.")
        if get_user_model().objects.filter(username__startswith=SIMULATION_PREFIX).exists():
            raise CommandError(
                "This simulation database already contains sim-* records. Use a new temporary root."
            )
        return temp_root

    def _report_path(self, value, temp_root):
        if not value:
            return None
        path = Path(value).expanduser().resolve()
        if temp_root not in path.parents:
            raise CommandError("The report path must be beneath the system temporary folder.")
        if path.name.lower() in {"db.sqlite3", "database.sqlite3"}:
            raise CommandError("The report path cannot replace a database file.")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _sanitized(result):
        return {key: value for key, value in result.items() if key != "credentials"}

    def handle(self, *args, **options):
        temp_root = self._guard()
        report_path = self._report_path(options.get("report"), temp_root)
        try:
            result = run_full_lifecycle()
        except Exception as exc:
            failure = {
                "scenario": options.get("scenario", "full-lifecycle"),
                "passed": False,
                "error": str(exc),
            }
            if report_path:
                report_path.write_text(json.dumps(failure, indent=2), encoding="utf-8")
            raise CommandError(f"Simulation failed: {exc}") from exc

        sanitized = self._sanitized(result)
        if report_path:
            report_path.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS("Grand Coast full-lifecycle simulation passed."))
        self.stdout.write(f"Project ID: {result['pilot']['project_id']}")
        self.stdout.write("Pilot user IDs:")
        for role, user_id in result["pilot"]["user_ids"].items():
            self.stdout.write(f"  {role}: {user_id}")
        self.stdout.write("Temporary dummy credentials (simulation only):")
        for role, credential in result["credentials"].items():
            self.stdout.write(f"  {role}: {credential['username']} / {credential['password']}")
        user_ids = ",".join(result["pilot"]["user_ids"].values())
        self.stdout.write("")
        self.stdout.write("Copy-ready pilot environment:")
        self.stdout.write("  GCC_EXECUTION_LOOP_ENABLED=true")
        self.stdout.write(f"  GCC_EXECUTION_LOOP_PROJECT_IDS={result['pilot']['project_id']}")
        self.stdout.write(f"  GCC_EXECUTION_LOOP_USER_IDS={user_ids}")
        self.stdout.write("  GCC_AI_ENABLED=false")
        self.stdout.write("  GCC_EMAIL_DELIVERY_ENABLED=false")
        self.stdout.write("  EXPO_PUSH_ENABLED=false")
        if report_path:
            self.stdout.write(f"JSON report: {report_path}")
        if options.get("json"):
            self.stdout.write(json.dumps(sanitized, indent=2))
