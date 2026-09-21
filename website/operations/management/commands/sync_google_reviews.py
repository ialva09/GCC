from django.core.management.base import BaseCommand, CommandError

from operations.google_reviews import (
    GoogleReviewsConfigurationError,
    GoogleReviewsFetchError,
    sync_google_reviews,
)


class Command(BaseCommand):
    help = "Fetch and cache the latest Google Places reviews."

    def handle(self, *args, **options):
        try:
            result = sync_google_reviews()
        except (GoogleReviewsConfigurationError, GoogleReviewsFetchError) as exc:
            raise CommandError(str(exc)) from exc

        display_name = result["display_name"] or "configured place"
        rating = result["rating"]
        total = result["review_count"]
        cached = result["review_count_cached"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Synced {cached} Google reviews for {display_name} "
                f"({rating:.1f}/5 from {total} total ratings)."
            )
        )