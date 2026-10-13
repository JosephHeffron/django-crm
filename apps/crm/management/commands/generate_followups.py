from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.crm.followups import generate_follow_ups


class Command(BaseCommand):
    help = (
        "Create follow-up tasks for customers due for repeat service. "
        "Idempotent — safe to run daily (Phase 19 schedules it)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Treat this date (YYYY-MM-DD) as today.")

    def handle(self, *args, **options):
        today = timezone.localdate()
        if options["date"]:
            today = parse_date(options["date"])
            if today is None:
                raise CommandError(f"Not a date: {options['date']!r} (expected YYYY-MM-DD)")
        skipped = []
        created = generate_follow_ups(today, skipped=skipped)
        self.stdout.write(f"Created {len(created)} follow-up task(s) for {today}.")
        if skipped:
            # A non-zero exit, so systemd records a failure. Zero
            # created is the normal healthy result most days; zero
            # created *because nobody could be assigned* is not, and
            # the two are indistinguishable from the journal otherwise.
            raise CommandError(
                f"{len(skipped)} follow-up(s) were due and could not be assigned: "
                + "; ".join(f"{contact} ({service.name})" for contact, service in skipped)
                + ". Give the customer an active owner, or make sure at least one "
                "active Owner-group user exists."
            )
