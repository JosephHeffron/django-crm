"""Fill a development database with realistic demo data, so every page
has something real to show.

    python manage.py seed_demo            # add demo data
    python manage.py seed_demo --reset    # remove it and add it fresh

Every demo row is created by, or belongs to, a ``demo_`` user — that is
how ``--reset`` finds exactly what to remove. Your own users and records
are never modified (follow-ups are generated for demo contacts only),
and reference data (service catalog, channels) is kept. The one addition
to real accounts: channel memberships, so you can read the demo team
chat when logged in as yourself.
Phone numbers use the reserved 555-01xx range and emails example.com:
no real people. Generation is seeded, so runs are reproducible.

Refuses to run unless DEBUG is on (or --force): this is never for
production.
"""

import os
import random
import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Goal, Notification
from apps.core.notifications import notify
from apps.crm.followups import generate_follow_ups, record_completion
from apps.crm.models import (
    Activity,
    BusinessPlan,
    Company,
    Contact,
    Note,
    PlanChecklistItem,
    Property,
    Tag,
    Task,
)
from apps.jobs.calendar import day_bounds
from apps.jobs.models import (
    Expense,
    Invoice,
    InvoiceLineItem,
    Job,
    JobAssignment,
    JobLineItem,
    Payment,
    Quote,
    QuoteLineItem,
    ServiceType,
    TimeEntry,
)
from apps.jobs.reports import invoiced_revenue
from apps.messaging.models import Channel, ChannelMembership, Message
from apps.messaging.services import direct_channel, visible_channels
from apps.users.models import get_profile
from apps.users.roles import Role

User = get_user_model()
DEMO_PREFIX = "demo_"

# username, first, last, role, title, calendar tone
DEMO_USERS = [
    ("demo_owner", "Olivia", "Grant", Role.OWNER, "Owner", 1),
    ("demo_sam", "Sam", "Rivera", Role.SALES_REP, "Sales Rep", 2),
    ("demo_riley", "Riley", "Chen", Role.SALES_REP, "Sales Rep", 5),
    ("demo_casey", "Casey", "Brooks", Role.CLEANER, "Crew Lead", 6),
    ("demo_jordan", "Jordan", "Price", Role.CLEANER, "Technician", 7),
    ("demo_alex", "Alex", "Morgan", Role.CLEANER, "Technician", 8),
    ("demo_taylor", "Taylor", "Nguyen", Role.CLEANER, "Technician", 10),
]
DEMO_TAGS = ["VIP", "Commercial", "Dog on property", "Gate code", "Annual plan", "Referral partner"]

FIRST_NAMES = (
    "James Mary Robert Patricia John Jennifer Michael Linda David Elizabeth William Barbara "
    "Richard Susan Joseph Jessica Thomas Sarah Charles Karen Daniel Lisa Matthew Nancy "
    "Anthony Betty Mark Sandra Paul Ashley Steven Emily Andrew Donna Kevin Michelle Brian "
    "Carol George Amanda"
).split()
LAST_NAMES = (
    "Smith Johnson Williams Brown Jones Garcia Miller Davis Wilson Anderson Taylor Thomas "
    "Moore Jackson Martin Lee Thompson White Harris Clark Lewis Robinson Walker Young Allen "
    "King Wright Scott Hill Green Adams Baker Nelson Carter Mitchell Roberts Turner Phillips "
    "Campbell Parker"
).split()
# Real towns, real postcodes and real roads around Rochester, NY, with
# arbitrary house numbers — so the Map page demonstrates a lookup that
# actually works.
#
# This replaces invented streets in invented towns ("119 Pine Ln, Cedar
# Hills, NY 14526"), which had no real-world referent, so OpenStreetMap
# correctly refused every one of them and the map looked broken. See
# the addendum to docs/decisions/0011-openstreetmap-map.md.
#
# The privacy line: these are public thoroughfares, not dwellings. The
# house numbers are made up and are not checked against any real
# address, so no seeded row says where any real household lives — which
# is the project's synthetic-data-only rule. Nominatim resolves
# "<road>, <town>, NY <postcode>" to the road whether or not that
# number exists on it, which is all the demo needs.
#
# Each town carries its own approximate centre, so a seeded pin lands
# in the right town instead of scattered around one point. Coordinates
# are committed here rather than looked up: seeding must never touch
# the network, and tests depend on that.
TOWNS = [
    # (town, postcode, latitude, longitude, roads in that town)
    ("Pittsford", "14534", 43.0906, -77.5147, ["Monroe Ave", "Clover St", "Jefferson Rd"]),
    ("Penfield", "14526", 43.1300, -77.4458, ["Penfield Rd", "Baird Rd", "Jackson Rd"]),
    ("Fairport", "14450", 43.0987, -77.4419, ["Main St", "Turk Hill Rd", "Ayrault Rd"]),
    ("Webster", "14580", 43.2117, -77.4283, ["Ridge Rd", "Holt Rd", "Phillips Rd"]),
    ("Rochester", "14618", 43.1192, -77.5597, ["Elmwood Ave", "Highland Ave", "Winton Rd"]),
    ("Rochester", "14625", 43.1636, -77.5083, ["Blossom Rd", "Creek St", "Browncroft Blvd"]),
]
# A few addresses are deliberately left unplaced, so the Map page's
# "Still to place" list, its "Look it up" button and the pin-drop form
# all have something to demonstrate. Every seeded address used to be
# pre-placed, which left that whole half of the page looking broken.
UNPLACED_IN_EVERY = 12
COMPANIES = ["Summit Property Management", "Lakeside HOA", "Keystone Rentals"]

# slug: (profile weight, quantity range, price override choices)
SERVICE_PROFILE = {
    "window-washing-exterior": (60, (12, 36), None),
    "window-washing-interior": (25, (10, 30), None),
    "gutter-cleaning": (55, (1, 1), None),
    "pressure-washing": (35, (600, 2400), None),
    "siding-cleaning": (20, (1, 1), None),
    "weed-removal": (20, (2, 6), None),
    "tree-removal": (5, (1, 1), ["450", "650", "900", "1200"]),
    "mulching": (25, (3, 10), None),
    "trimming": (30, (2, 5), None),
}

CREW_MESSAGES = [
    "Heads up — the Maple Grove job has a locked side gate, code is in the job notes.",
    "Running about 20 minutes behind, traffic on the parkway.",
    "Need another bottle of window solution for tomorrow.",
    "Finished early at the {job}, heading to the next one.",
    "Ladder stabilizer on truck 2 is loose, don't use it until it's fixed.",
    "Customer asked if we can come back for the back windows next week.",
    "Rain in the forecast Thursday afternoon — might need to shuffle jobs.",
]
SALES_MESSAGES = [
    "Sent the quote for {contact} — they want gutters and windows together.",
    "{contact} accepted! Can we get them on the schedule next week?",
    "Following up with {contact} tomorrow, they were comparing prices.",
    "Referral came in from {contact}, adding them as a lead.",
    "Anyone tried bundling pressure washing with siding? Two people asked this week.",
]
GENERAL_MESSAGES = [
    "Great work this week everyone — highest number of jobs completed this month!",
    "Reminder: team meeting Monday at 7:30 before we head out.",
    "New uniforms are in the shop, grab your size.",
    "Fall gutter season is coming — expect the schedule to fill up fast.",
]


class Command(BaseCommand):
    help = "Fill a development database with realistic demo data (DEBUG only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Remove existing demo data (only demo_ rows) before seeding.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow running with DEBUG off. Never in production.",
        )
        parser.add_argument("--seed", type=int, default=17, help="Random seed (reproducible data).")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("seed_demo only runs with DEBUG on (pass --force to override).")
        demo_exists = User.objects.filter(username__startswith=DEMO_PREFIX).exists()
        if demo_exists and not options["reset"]:
            raise CommandError("Demo data already exists. Use --reset to replace it.")

        password = os.environ.get("DEMO_USER_PASSWORD")
        generated = password is None
        if generated:
            password = secrets.token_urlsafe(9)

        with transaction.atomic():
            if demo_exists:
                removed = remove_demo_data()
                self.stdout.write(f"Removed existing demo data ({removed} demo users).")
            # Seeded PRNG on purpose: reproducible fake data, not security.
            # The demo password above comes from `secrets`.
            rng = random.Random(options["seed"])  # nosec B311
            counts = DemoSeeder(rng, password).run()

        self.stdout.write(self.style.SUCCESS("Demo data created:"))
        for label, value in counts.items():
            self.stdout.write(f"  {label}: {value}")
        users = ", ".join(u[0] for u in DEMO_USERS)
        self.stdout.write(f"Demo logins: {users}")
        if generated:
            self.stdout.write(
                f"Demo password (shown once; set DEMO_USER_PASSWORD to choose one): {password}"
            )


def remove_demo_data():
    """Delete every row created by or belonging to demo_ users, children
    before parents (the FKs involved are PROTECT). Returns the number of
    demo users removed."""
    demo_users = User.objects.filter(username__startswith=DEMO_PREFIX)
    demo_contacts = Contact.objects.filter(created_by__in=demo_users)
    demo_jobs = Job.objects.filter(created_by__in=demo_users)

    TimeEntry.objects.filter(user__in=demo_users).delete()
    Notification.objects.filter(recipient__in=demo_users).delete()
    # Goals aren't owned by a user, so they'd survive the user delete.
    Goal.objects.all().delete()
    Message.objects.filter(author_user__in=demo_users).delete()
    # Direct messages with a demo user (including any a real user started
    # with one) go with the demo.
    Channel.objects.filter(
        kind=Channel.Kind.DIRECT,
        pk__in=ChannelMembership.objects.filter(user__in=demo_users).values("channel_id"),
    ).delete()
    Payment.objects.filter(invoice__job__in=demo_jobs).delete()
    Invoice.objects.filter(job__in=demo_jobs).delete()
    Task.objects.filter(created_by__in=demo_users).delete()
    Task.objects.filter(contact__in=demo_contacts).delete()
    Note.objects.filter(author__in=demo_users).delete()
    Activity.objects.filter(created_by__in=demo_users).delete()
    demo_jobs.delete()
    Quote.objects.filter(prepared_by__in=demo_users).delete()
    Expense.objects.filter(recorded_by__in=demo_users).delete()
    BusinessPlan.objects.filter(created_by__in=demo_users).delete()
    demo_contacts.delete()
    Company.objects.filter(created_by__in=demo_users).delete()
    Tag.objects.filter(name__in=DEMO_TAGS, contacts__isnull=True).delete()
    removed = demo_users.count()
    demo_users.delete()
    return removed


class DemoSeeder:
    def __init__(self, rng, password):
        self.rng = rng
        self.password = password
        self.now = timezone.localtime()
        self.today = self.now.date()
        self.services = {s.slug: s for s in ServiceType.objects.all()}
        # Counted so a predictable few are left for the Map page's
        # "Still to place" list to show (see UNPLACED_IN_EVERY).
        self.addresses_made = 0

    # ---------- helpers ----------

    def at(self, day, hour, minute=0):
        return timezone.make_aware(datetime.combine(day, time(hour, minute)))

    def weekday_back(self, days):
        day = self.today - timedelta(days=days)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        return day

    def pick_weighted(self, options):
        return self.rng.choices(list(options), weights=[w for w, *_ in options.values()])[0]

    def line_for(self, slug):
        _, (low, high), prices = SERVICE_PROFILE[slug]
        service = self.services[slug]
        price = Decimal(self.rng.choice(prices)) if prices else service.default_price
        return service, Decimal(self.rng.randint(low, high)), price

    # ---------- steps ----------

    def run(self):
        self.users()
        self.contacts()
        self.history()
        self.upcoming()
        self.quotes()
        self.activities()
        self.tasks()
        self.plans_and_notes()
        self.expenses()
        self.messages()
        goal_count = self.goals()
        clocked = self.time_entries()
        return {
            "users": len(DEMO_USERS),
            "contacts": Contact.objects.filter(created_by__in=self.all_users).count(),
            "jobs": Job.objects.filter(created_by__in=self.all_users).count(),
            "quotes": Quote.objects.filter(prepared_by__in=self.all_users).count(),
            "invoices": Invoice.objects.filter(job__created_by__in=self.all_users).count(),
            "follow-ups": self.follow_up_count,
            "messages": Message.objects.filter(author_user__in=self.all_users).count(),
            "notifications": Notification.objects.filter(recipient__in=self.all_users).count(),
            "goals": goal_count,
            "time entries": clocked,
        }

    def users(self):
        self.by_role = {role: [] for role in Role}
        for username, first, last, role, title, tone in DEMO_USERS:
            user = User.objects.create_user(
                username,
                password=self.password,
                first_name=first,
                last_name=last,
                email=f"{username}@example.com",
            )
            user.groups.add(Group.objects.get(name=role.value))
            profile = get_profile(user)
            profile.title = title
            profile.phone = f"(585) 555-01{len(self.by_role[role]) + tone:02d}"
            profile.calendar_tone = tone
            # Crew get a pay rate and weekday hours so Payroll and
            # Assignments have something real to work from.
            if role == Role.CLEANER:
                profile.hourly_rate = Decimal("21.00") + tone
                profile.working_days = "01234" if tone % 2 else "012345"
            profile.save()
            self.by_role[role].append(user)
        self.all_users = [u for users in self.by_role.values() for u in users]
        self.owner = self.by_role[Role.OWNER][0]
        self.reps = self.by_role[Role.SALES_REP]
        self.crew = self.by_role[Role.CLEANER]

    def contacts(self):
        tags = {name: Tag.objects.get_or_create(name=name)[0] for name in DEMO_TAGS}
        companies = [
            Company.objects.create(name=name, phone="(585) 555-0100", created_by=self.owner)
            for name in COMPANIES
        ]
        sources = [s for s, _ in Contact.LeadSource.choices]
        used = set()
        self.customers, self.leads = [], []
        for index in range(60):
            while True:
                first, last = self.rng.choice(FIRST_NAMES), self.rng.choice(LAST_NAMES)
                if (first, last) not in used:
                    used.add((first, last))
                    break
            is_lead = index % 10 < 3
            company = companies[index % 3] if index < 9 else None
            contact = Contact.objects.create(
                first_name=first,
                last_name=last,
                email=f"{first}.{last}@example.com".lower(),
                phone=f"(585) 555-01{index:02d}",
                status=Contact.Status.LEAD if is_lead else Contact.Status.CUSTOMER,
                lead_source=self.rng.choices(sources, weights=[30, 20, 12, 10, 5, 5, 15, 3])[0],
                preferred_contact_method=self.rng.choice(["call", "text", "text", "email"]),
                company=company,
                owner=self.rng.choice(self.reps),
                created_by=self.owner,
            )
            chosen = [tags["Commercial"]] if company else []
            chosen += self.rng.sample(
                [t for n, t in tags.items() if n != "Commercial"], k=self.rng.randint(0, 2)
            )
            contact.tags.set(chosen)
            self.add_property(contact, primary=True)
            if self.rng.random() < 0.1:
                self.add_property(contact, primary=False, label="Rental")
            contact.profile_services = list(
                dict.fromkeys(
                    self.pick_weighted(SERVICE_PROFILE) for _ in range(self.rng.randint(1, 3))
                )
            )
            (self.leads if is_lead else self.customers).append(contact)

    def add_property(self, contact, primary, label="Home"):
        town, postal, lat, lng, roads = self.rng.choice(TOWNS)
        number = self.rng.randint(12, 980)
        address = Property(
            contact=contact,
            label=label,
            street=f"{number} {self.rng.choice(roads)}",
            city=town,
            state="NY",
            postal_code=postal,
            notes=self.rng.choice(
                ["", "", "Gate code 4412", "Dog in back yard", "Park in driveway"]
            ),
            is_primary=primary,
        )
        self.addresses_made += 1
        if self.addresses_made % UNPLACED_IN_EVERY:
            # Placed from the town's own committed centre, with a small
            # scatter so pins don't stack. Never looked up: seeding must
            # work with no network at all (ADR 0011).
            address.latitude = Decimal(f"{lat + self.rng.uniform(-0.012, 0.012):.6f}")
            address.longitude = Decimal(f"{lng + self.rng.uniform(-0.015, 0.015):.6f}")
            address.located_at = self.now
            address.located_address = str(address)[:400]
        address.save()
        return address

    def make_job(self, contact, slugs, day, hour, status, quote=None):
        lines = [self.line_for(slug) for slug in dict.fromkeys(slugs)]
        subtotal = sum(q * p for _, q, p in lines)
        duration = min(max(float(subtotal) / 120, 1.5), 6)
        start = self.at(day, hour)
        end = start + timedelta(hours=duration)
        if status is None:  # by the clock (today's jobs)
            if end <= self.now:
                status = Job.Status.COMPLETED
            elif start <= self.now:
                status = Job.Status.IN_PROGRESS
            else:
                status = Job.Status.SCHEDULED
        job = Job.objects.create(
            contact=contact,
            service_property=contact.properties.filter(is_primary=True).first(),
            quote=quote,
            sales_rep=contact.owner,
            primary_service_type=lines[0][0],
            status=status,
            scheduled_start=start,
            scheduled_end=end,
            completed_at=end if status == Job.Status.COMPLETED else None,
            customer_rating=(
                self.rng.choices([5, 4, 3], weights=[70, 25, 5])[0]
                if status == Job.Status.COMPLETED and self.rng.random() < 0.55
                else None
            ),
            created_by=self.owner,
        )
        for position, (service, qty, price) in enumerate(lines):
            JobLineItem.objects.create(
                job=job, service_type=service, quantity=qty, unit_price=price, position=position
            )
        hours = Decimal(str(round(duration, 2)))
        for member in self.rng.sample(self.crew, k=self.rng.randint(1, 2)):
            JobAssignment.objects.create(
                job=job,
                user=member,
                hours_worked=hours if status == Job.Status.COMPLETED else None,
            )
        return job

    def invoice(self, job):
        issued = timezone.localdate(job.completed_at)
        age = (self.today - issued).days
        draft = age <= 2 and self.rng.random() < 0.5
        invoice = Invoice.objects.create(
            job=job,
            contact=job.contact,
            issued_on=issued,
            due_on=issued + timedelta(days=14),
            status=Invoice.Status.DRAFT if draft else Invoice.Status.SENT,
        )
        for line in job.line_items.all():
            InvoiceLineItem.objects.create(
                invoice=invoice,
                service_type=line.service_type,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                position=line.position,
            )
        if draft:
            return
        paid_full, partial = (0.92, 0.05) if age > 30 else (0.6, 0.15)
        roll = self.rng.random()
        total = invoice.total
        if roll < paid_full + partial:
            amount = total if roll < paid_full else (total / 2).quantize(Decimal("0.01"))
            received = min(issued + timedelta(days=self.rng.randint(0, 20)), self.today)
            Payment.objects.create(
                invoice=invoice,
                amount=amount,
                received_on=received,
                method=self.rng.choices(["card", "check", "cash", "transfer"], [50, 30, 10, 10])[0],
                recorded_by=self.owner,
            )

    def history(self):
        """12 months of completed work, following each customer's usual
        services and each service's repeat interval."""
        for contact in self.customers:
            visits = {}
            for slug in contact.profile_services:
                interval = self.services[slug].followup_interval_months or 18
                days_ago = self.rng.randint(10, 400)
                while days_ago <= 380:
                    visits.setdefault(self.weekday_back(days_ago), []).append(slug)
                    days_ago += interval * 30 + self.rng.randint(-10, 10)
            for day, slugs in sorted(visits.items()):
                job = self.make_job(
                    contact, slugs, day, self.rng.choice([8, 9, 10, 11, 13]), Job.Status.COMPLETED
                )
                self.invoice(job)

    def upcoming(self):
        """Today's jobs (status by the clock) and the next three weeks."""
        for hour in (8, 11, 14):
            contact = self.rng.choice(self.customers)
            job = self.make_job(contact, contact.profile_services[:1], self.today, hour, None)
            if job.status == Job.Status.COMPLETED:
                self.invoice(job)
        for offset in range(1, 22):
            day = self.today + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            for hour in self.rng.sample([8, 10, 13], k=self.rng.randint(1, 3)):
                contact = self.rng.choice(self.customers)
                self.make_job(contact, contact.profile_services, day, hour, Job.Status.SCHEDULED)

    def quote(self, contact, status, created_days_ago, site_visit=None):
        quote = Quote.objects.create(
            contact=contact,
            service_property=contact.properties.filter(is_primary=True).first(),
            status=status,
            prepared_by=contact.owner,
            site_visit_at=site_visit,
            sent_at=(
                self.now - timedelta(days=max(created_days_ago - 1, 0))
                if status != Quote.Status.DRAFT
                else None
            ),
            expires_on=self.today + timedelta(days=30 - created_days_ago),
            accepted_at=(
                self.now - timedelta(days=max(created_days_ago - 3, 0))
                if status == Quote.Status.ACCEPTED
                else None
            ),
        )
        for position, slug in enumerate(dict.fromkeys(contact.profile_services)):
            service, qty, price = self.line_for(slug)
            QuoteLineItem.objects.create(
                quote=quote, service_type=service, quantity=qty, unit_price=price, position=position
            )
        Quote.objects.filter(pk=quote.pk).update(
            created_at=self.now - timedelta(days=created_days_ago)
        )
        return quote

    def quotes(self):
        for index, lead in enumerate(self.leads):
            status = [Quote.Status.DRAFT, Quote.Status.SENT, Quote.Status.SENT][index % 3]
            visit = None
            if index % 2 == 0:
                visit_day = self.today + timedelta(days=self.rng.randint(1, 10))
                visit = self.at(visit_day, self.rng.choice([9, 12, 15, 16]))
            self.quote(lead, status, self.rng.randint(1, 20), site_visit=visit)
        for contact in self.rng.sample(self.customers, k=6):
            quote = self.quote(contact, Quote.Status.ACCEPTED, self.rng.randint(3, 15))
            day = self.today + timedelta(days=self.rng.randint(2, 18))
            while day.weekday() >= 5:
                day += timedelta(days=1)
            self.make_job(contact, contact.profile_services, day, 9, Job.Status.SCHEDULED, quote)
        for contact in self.rng.sample(self.customers, k=3):
            self.quote(contact, Quote.Status.DECLINED, self.rng.randint(20, 60))
        for contact in self.rng.sample(self.customers, k=2):
            self.quote(contact, Quote.Status.EXPIRED, self.rng.randint(45, 90))

    def activities(self):
        kinds = [
            (Activity.ActivityType.CALL, "Called about {s}"),
            (Activity.ActivityType.TEXT, "Texted appointment reminder"),
            (Activity.ActivityType.EMAIL, "Emailed quote for {s}"),
            (Activity.ActivityType.VISIT, "Site visit to measure for {s}"),
        ]
        # Sparse and mostly older: every Activity is a contact touch that
        # resets follow-up clocks, so dense recent history would leave the
        # demo with almost no follow-ups due.
        for contact in self.customers + self.leads:
            for _ in range(self.rng.randint(0, 3)):
                kind, subject = self.rng.choice(kinds)
                service = self.services[self.rng.choice(contact.profile_services)].name.lower()
                activity = Activity.objects.create(
                    activity_type=kind,
                    subject=subject.format(s=service),
                    contact=contact,
                    created_by=contact.owner,
                )
                # Activity.save() forbids updates by design; back-dating the
                # seed's history uses a queryset update, which it allows.
                Activity.objects.filter(pk=activity.pk).update(
                    created_at=self.now - timedelta(days=self.rng.randint(20, 400))
                )

    def tasks(self):
        # Real follow-up generation, then some completed and some overdue.
        follow_ups = generate_follow_ups(
            self.today, contact_ids=[c.pk for c in self.customers + self.leads]
        )
        self.follow_up_count = len(follow_ups)
        for index, task in enumerate(follow_ups):
            if index % 5 == 4:
                task.status = Task.Status.COMPLETED
                task.completed_at = self.now - timedelta(days=self.rng.randint(0, 5))
                record_completion(task, task.assigned_to)
                task.save()
            elif index % 3 == 0:
                task.due_date = self.today - timedelta(days=self.rng.randint(1, 20))
                task.save(update_fields=["due_date"])
        titles = [
            "Order more gutter guards",
            "Call back about pressure washing estimate",
            "Update Google Business photos",
            "Confirm Saturday crew availability",
            "Send thank-you cards to referral customers",
            "Renew van registration",
            "Review negative review response",
            "Price out a second ladder rack",
            "Schedule truck oil change",
            "Prepare spring promo flyer",
            "Check in with Summit Property Management",
            "Train new crew member on water-fed pole",
        ]
        for index, title in enumerate(titles):
            assignee = self.rng.choice(self.reps + [self.owner])
            completed = index % 4 == 3
            task = Task.objects.create(
                title=title,
                assigned_to=assignee,
                contact=self.rng.choice(self.customers) if index % 3 == 0 else None,
                due_date=self.today + timedelta(days=self.rng.randint(-10, 14)),
                priority=self.rng.choice(["low", "medium", "medium", "high"]),
                status=Task.Status.COMPLETED if completed else Task.Status.PENDING,
                completed_at=self.now - timedelta(days=2) if completed else None,
                completed_by=assignee if completed else None,
                created_by=self.owner,
            )
            # Same announcement the task form makes, so the bell has the
            # history it would really have. (Follow-up notifications come
            # from generate_follow_ups above.)
            if not completed and assignee != self.owner:
                notify(
                    assignee,
                    Notification.Kind.TASK,
                    f"{self.owner.get_full_name()} assigned you a task",
                    task.title,
                    task.get_absolute_url(),
                    event=f"task:{task.pk}",
                )

    def time_entries(self):
        """Clocked time for the crew over the last fortnight, on the
        jobs they actually worked — so Payroll and the time clock show a
        real week rather than an empty one."""
        done = list(
            Job.objects.filter(
                status=Job.Status.COMPLETED, completed_at__gte=self.now - timedelta(days=14)
            ).prefetch_related("assignments")[:40]
        )
        made = 0
        for job in done:
            for assignment in job.assignments.all():
                hours = assignment.hours_worked or Decimal("2")
                started = job.scheduled_start
                TimeEntry.objects.create(
                    user=assignment.user,
                    job=job,
                    started_at=started,
                    ended_at=started + timedelta(hours=float(hours)),
                )
                made += 1
        return made

    def goals(self):
        """Targets a little above what this month has actually done, so
        the dashboard shows progress rather than a goal already met."""
        first = self.today.replace(day=1)
        revenue = invoiced_revenue(first, self.today)
        completed = Job.objects.filter(
            status=Job.Status.COMPLETED, completed_at__gte=day_bounds(first, self.today)[0]
        ).count()
        targets = {
            Goal.Metric.REVENUE: (revenue * Decimal("1.3")).quantize(Decimal("1"))
            or Decimal("8000"),
            Goal.Metric.JOBS: Decimal(max(completed + 4, 10)),
            Goal.Metric.CUSTOMERS: Decimal("6"),
        }
        for metric, target in targets.items():
            Goal.objects.update_or_create(metric=metric, defaults={"target": target})
        return len(targets)

    def plans_and_notes(self):
        plans = [
            (
                "Launch gutter-guard upsell",
                BusinessPlan.Status.IN_PROGRESS,
                45,
                [
                    "Pick a supplier",
                    "Set install pricing",
                    "Train crew",
                    "Email past gutter customers",
                ],
                2,
            ),
            (
                "Hire two seasonal crew members",
                BusinessPlan.Status.NOT_STARTED,
                60,
                [
                    "Post job listing",
                    "Interview candidates",
                    "Order uniforms",
                    "Ride-along training",
                ],
                0,
            ),
            (
                "Hit $120k revenue this year",
                BusinessPlan.Status.IN_PROGRESS,
                95,
                ["Raise window pricing 5%", "Launch referral discount", "Add a fall promo"],
                1,
            ),
        ]
        for title, status, due_in, items, done in plans:
            plan = BusinessPlan.objects.create(
                title=title,
                owner=self.owner,
                status=status,
                due_date=self.today + timedelta(days=due_in),
                priority="high",
                created_by=self.owner,
            )
            for position, text in enumerate(items):
                PlanChecklistItem.objects.create(
                    plan=plan, text=text, is_done=position < done, position=position
                )
        contact_notes = [
            "Prefers texts, not calls, before 9am.",
            "Asked about bundling windows and gutters for a discount.",
            "Side gate sticks — lift and push.",
            "Very happy with last visit, mentioned telling neighbors.",
            "Wants a quote for the detached garage next time.",
        ]
        for text in contact_notes:
            Note.objects.create(
                author=self.rng.choice(self.reps),
                body=text,
                contact=self.rng.choice(self.customers),
            )
        Note.objects.create(
            author=self.owner,
            body="Price increase on window cleaning takes effect next month.",
            pinned=True,
        )
        Note.objects.create(
            author=self.owner, body="Truck 2 is due for inspection by the 15th.", pinned=True
        )
        job = Job.objects.filter(status=Job.Status.SCHEDULED).first()
        if job:
            Note.objects.create(
                author=self.crew[0], body="Bring the extension pole — 3rd floor windows.", job=job
            )

    def expenses(self):
        for month in range(12):
            day = self.today.replace(day=1) - timedelta(days=30 * month)
            rows = [
                ("fuel", self.rng.randint(380, 560), "Fuel — both trucks"),
                ("supplies", self.rng.randint(220, 480), "Cleaning solution, squeegees, bags"),
                ("insurance", 350, "General liability"),
            ]
            if month % 2 == 0:
                rows.append(("marketing", self.rng.randint(120, 400), "Mailers and online ads"))
            if month in (2, 7):
                rows.append(("equipment", self.rng.randint(800, 2400), "Pressure washer parts"))
            for category, amount, description in rows:
                Expense.objects.create(
                    date=day,
                    amount=Decimal(amount),
                    category=category,
                    description=description,
                    recorded_by=self.owner,
                )

    def messages(self):
        """Team channels and a couple of DMs over the last ten days, with
        read markers that leave each person a few unread."""
        people = self.all_users + list(
            User.objects.filter(is_active=True).exclude(username__startswith=DEMO_PREFIX)
        )
        jobs = list(Job.objects.filter(created_by=self.owner, status=Job.Status.SCHEDULED)[:10])
        plan = {
            "general": (GENERAL_MESSAGES, [self.owner] + self.reps),
            "crew": (CREW_MESSAGES, self.crew + [self.owner]),
            "sales": (SALES_MESSAGES, self.reps + [self.owner]),
        }
        for slug, (templates, authors) in plan.items():
            channel = Channel.objects.get(slug=slug)
            self.post_thread(channel, templates, authors, jobs, count=12)
            # Only people who can read it (#sales is Owner and sales reps).
            self.join(
                channel, [p for p in people if visible_channels(p).filter(pk=channel.pk).exists()]
            )
        for a, b in ((self.owner, self.reps[0]), (self.crew[0], self.crew[1])):
            # The app's own helper, so opening this DM in the app finds
            # this channel rather than starting a second one.
            channel = direct_channel(a, b)
            self.post_thread(
                channel,
                ["Can you cover {contact} on Friday?", "Yep, I've got it.", "Thanks!"],
                [a, b],
                jobs,
                count=5,
            )
            self.join(channel, [a, b])

    def post_thread(self, channel, templates, authors, jobs, count):
        # Oldest first, so posting order and timestamps agree.
        hours_ago = sorted((self.rng.randint(1, 240) for _ in range(count)), reverse=True)
        for index in range(count):
            contact = self.rng.choice(self.customers)
            job = self.rng.choice(jobs) if jobs else None
            template = self.rng.choice(templates)
            names_contact = "{contact}" in template
            message = Message.objects.create(
                channel=channel,
                author_user=authors[index % len(authors)],
                body=template.format(contact=contact, job=job.number if job else ""),
                ref_contact=contact if names_contact or self.rng.random() < 0.2 else None,
                ref_job=job if channel.slug == "crew" and self.rng.random() < 0.4 else None,
            )
            Message.objects.filter(pk=message.pk).update(
                created_at=self.now - timedelta(hours=hours_ago[index])
            )

    def join(self, channel, users):
        ordered = list(channel.messages.order_by("created_at", "pk"))
        for user in users:
            unread = self.rng.randint(0, 4)
            last_read = ordered[-1 - unread] if len(ordered) > unread else None
            ChannelMembership.objects.update_or_create(
                channel=channel, user=user, defaults={"last_read_message": last_read}
            )
