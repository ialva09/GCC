from django.core.management.base import BaseCommand

from operations.security import retry_pending_admin_security_emails


class Command(BaseCommand):
    help = "Retry pending and failed Grand Coast administration security alert emails."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        count = retry_pending_admin_security_emails(limit=max(1, options["limit"]))
        self.stdout.write(self.style.SUCCESS(f"Attempted {count} security alert deliveries."))
