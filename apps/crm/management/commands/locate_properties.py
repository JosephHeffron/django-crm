"""Place service addresses on the map, in the background.

Nominatim allows one request a second, so this is deliberately a
command rather than something a page waits for. Run it after importing
customers, or on a timer alongside the follow-up generator.
"""

from django.core.management.base import BaseCommand

from apps.crm.geocoding import LookupError_, locate
from apps.crm.models import Property


class Command(BaseCommand):
    help = "Look up coordinates for service addresses that have none."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="How many addresses to look up in this run (default 50).",
        )
        parser.add_argument(
            "--redo",
            action="store_true",
            help="Also re-look-up addresses that have already been placed.",
        )

    def handle(self, *args, **options):
        properties = Property.objects.select_related("contact").order_by("pk")
        if not options["redo"]:
            properties = properties.filter(latitude__isnull=True)
        pending = [p for p in properties if options["redo"] or p.needs_locating]
        pending = pending[: options["limit"]]
        if not pending:
            self.stdout.write("Every address is already placed.")
            return

        located = missing = failed = 0
        for service_property in pending:
            try:
                result = locate(service_property)
            except LookupError_ as error:
                failed += 1
                self.stderr.write(f"{service_property}: {error}")
                continue
            if result == "located":
                located += 1
            else:
                missing += 1
                self.stdout.write(f"Not found: {service_property}")
        self.stdout.write(
            self.style.SUCCESS(f"Placed {located}, not found {missing}, service errors {failed}.")
        )
        if failed:
            self.stdout.write("Run it again later for the ones that errored.")
