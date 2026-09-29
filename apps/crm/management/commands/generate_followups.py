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
        created = generate_follow_ups(today)
        self.stdout.write(f"Created {len(created)} follow-up task(s) for {today}.")
