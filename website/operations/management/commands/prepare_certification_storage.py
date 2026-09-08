from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from operations.storage_certification import ensure_storage_bucket


class Command(BaseCommand):
    help = "Verify certification storage, optionally creating only a disposable emulator bucket."

    def add_arguments(self, parser):
        parser.add_argument("--create-if-missing", action="store_true")

    def handle(self, *args, **options):
        if not getattr(settings, "GCC_SIMULATION_MODE", False):
            raise CommandError("Refusing certification storage preparation outside simulation mode.")
        if not getattr(settings, "GCC_STORAGE_SMOKE_ENABLED", False):
            raise CommandError("Set GCC_STORAGE_SMOKE_ENABLED=true before preparing storage.")
        try:
            result = ensure_storage_bucket(create_if_missing=options["create_if_missing"])
        except AssertionError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Certification bucket is ready: {result['bucket']}"))
