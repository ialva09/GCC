from django.core.management.base import BaseCommand

from operations.notifications import retry_pending_push_deliveries


class Command(BaseCommand):
    help = 'Retry pending and failed Expo employee push notifications.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        count = retry_pending_push_deliveries(limit=max(1, options['limit']))
        self.stdout.write(self.style.SUCCESS(f'Attempted {count} push notification deliveries.'))
