from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from operations.storage_certification import cleanup_storage_prefix


class Command(BaseCommand):
    help = "Delete only the current guarded certification prefix from S3-compatible storage."

    def handle(self, *args, **options):
        prefix = str(getattr(settings, "GCC_STORAGE_PREFIX", "") or "").strip("/")
        if not getattr(settings, "GCC_SIMULATION_MODE", False):
            raise CommandError("Refusing certification cleanup outside GCC_SIMULATION_MODE.")
        if not prefix:
            raise CommandError("GCC_STORAGE_PREFIX is required for certification cleanup.")
        result = cleanup_storage_prefix()
        self.stdout.write(f"Deleted {result['deleted']} objects under {prefix}/.")
