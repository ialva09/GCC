from django.core.management.base import BaseCommand

from operations.email_delivery import dispatch_pending_email_outbox


class Command(BaseCommand):
    help = 'Deliver due Grand Coast email outbox items without changing business records.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        counts = dispatch_pending_email_outbox(limit=max(1, options['limit']))
        summary = (
            'Email outbox: attempted={attempted} sent={sent} '
            'failed={failed} pending={pending}'
        ).format(**counts)
        self.stdout.write(
            self.style.SUCCESS(summary)
        )
