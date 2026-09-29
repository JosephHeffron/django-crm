from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.crm.models import Property, Task
from apps.jobs.models import (
    Invoice,
    Job,
    JobAssignment,
    Payment,
    Photo,
    QuoteLineItem,
    ServiceType,
    photo_upload_to,
)
from apps.users.models import avatar_upload_to

from . import _factories as f


class ServiceCatalogSeedTests(TestCase):
    def test_default_services_seeded_with_follow_up_intervals(self):
        intervals = dict(ServiceType.objects.values_list("slug", "followup_interval_months"))
        self.assertEqual(len(intervals), 10)
        self.assertEqual(intervals["window-washing-exterior"], 6)
        self.assertEqual(intervals["gutter-cleaning"], 6)
        self.assertEqual(intervals["pressure-washing"], 12)
        self.assertEqual(intervals["weed-removal"], 3)
        self.assertIsNone(intervals["tree-removal"])

    def test_tone_class(self):
        self.assertEqual(f.service("gutter-cleaning").tone_class, "tone-2")


class DocumentTotalsTests(TestCase):
    def setUp(self):
        self.owner = f.user()
        self.contact = f.contact(self.owner)

    def test_quote_total_sums_quantity_times_price(self):
        q = f.quote(
            self.contact,
            self.owner,
            lines=[(Decimal("20"), Decimal("8.00")), (Decimal("1"), Decimal("175.00"))],
        )
        self.assertEqual(q.total, Decimal("335.00"))
        self.assertEqual(q.__class__.objects.with_totals().get(pk=q.pk).total, Decimal("335.00"))

    def test_empty_document_totals_zero_not_none(self):
        q = f.quote(self.contact, self.owner, lines=[])
        self.assertEqual(q.total, Decimal("0"))
        self.assertEqual(q.__class__.objects.with_totals().get(pk=q.pk).total, Decimal("0"))

    def test_number_derives_from_pk(self):
        j = f.job(self.contact, self.owner)
        self.assertEqual(j.number, f"J-{1000 + j.pk}")

    def test_invoice_balances_do_not_multiply_across_joins(self):
        # Two line items and two payments: a naive JOIN-based annotation
        # would double both sums (2 lines x 2 payments). Subqueries don't.
        inv = f.invoice(
            f.job(self.contact, self.owner),
            lines=[(Decimal("1"), Decimal("100")), (Decimal("1"), Decimal("50"))],
        )
        for amount in ("40", "20"):
            Payment.objects.create(
                invoice=inv,
                amount=Decimal(amount),
                received_on=date(2026, 10, 3),
                recorded_by=self.owner,
            )
        annotated = Invoice.objects.with_balances().get(pk=inv.pk)
        self.assertEqual(annotated.total, Decimal("150"))
        self.assertEqual(annotated.paid, Decimal("60"))
        self.assertEqual(annotated.balance_amount, Decimal("90"))
        self.assertEqual(inv.balance, Decimal("90"))


class InvoicePaymentStatusTests(TestCase):
    def setUp(self):
        owner = f.user()
        self.owner = owner
        self.inv = f.invoice(f.job(f.contact(owner), owner), issued=date(2026, 10, 1))
        self.before_due = date(2026, 10, 5)
        self.after_due = date(2026, 11, 1)

    def _pay(self, amount):
        Payment.objects.create(
            invoice=self.inv,
            amount=Decimal(amount),
            received_on=date(2026, 10, 2),
            recorded_by=self.owner,
        )

    def test_unpaid_then_overdue(self):
        self.assertEqual(self.inv.payment_status(self.before_due), "unpaid")
        self.assertEqual(self.inv.payment_status(self.after_due), "overdue")

    def test_partially_paid_and_paid(self):
        self._pay("75")
        self.assertEqual(self.inv.payment_status(self.before_due), "partially_paid")
        self._pay("100")
        self.assertEqual(self.inv.payment_status(self.after_due), "paid")

    def test_draft_and_void_are_not_outstanding(self):
        self.inv.status = Invoice.Status.DRAFT
        self.assertEqual(self.inv.payment_status(self.after_due), "draft")
        self.inv.status = Invoice.Status.VOID
        self.assertEqual(self.inv.payment_status(self.after_due), "void")


class ConstraintTests(TestCase):
    """Database-level guarantees, not just form validation."""

    def setUp(self):
        self.owner = f.user()
        self.contact = f.contact(self.owner)

    def assertRejected(self, fn):
        with self.assertRaises(IntegrityError), transaction.atomic():
            fn()

    def test_job_must_end_after_it_starts(self):
        start = f.aware(2026, 10, 1)
        self.assertRejected(
            lambda: Job.objects.create(
                contact=self.contact,
                created_by=self.owner,
                primary_service_type=f.service(),
                scheduled_start=start,
                scheduled_end=start - timedelta(minutes=1),
            )
        )

    def test_rating_between_1_and_5(self):
        j = f.job(self.contact, self.owner)
        Job.objects.filter(pk=j.pk).update(customer_rating=5)
        self.assertRejected(lambda: Job.objects.filter(pk=j.pk).update(customer_rating=6))

    def test_crew_member_assigned_once_per_job(self):
        j = f.job(self.contact, self.owner)
        crew = f.user("crew")
        f.assign(j, crew)
        self.assertRejected(lambda: JobAssignment.objects.create(job=j, user=crew))

    def test_line_quantity_must_be_positive(self):
        q = f.quote(self.contact, self.owner, lines=[])
        self.assertRejected(
            lambda: QuoteLineItem.objects.create(
                quote=q, service_type=f.service(), quantity=Decimal("0"), unit_price=Decimal("1")
            )
        )

    def test_payment_must_be_positive(self):
        inv = f.invoice(f.job(self.contact, self.owner))
        self.assertRejected(
            lambda: Payment.objects.create(
                invoice=inv,
                amount=Decimal("0"),
                received_on=date(2026, 10, 2),
                recorded_by=self.owner,
            )
        )

    def test_invoice_due_date_not_before_issue(self):
        j = f.job(self.contact, self.owner)
        self.assertRejected(
            lambda: Invoice.objects.create(
                job=j, contact=self.contact, issued_on=date(2026, 10, 2), due_on=date(2026, 10, 1)
            )
        )

    def test_photo_belongs_to_exactly_one_parent(self):
        self.assertRejected(lambda: Photo.objects.create(image="x.jpg", uploaded_by=self.owner))
        j = f.job(self.contact, self.owner)
        q = f.quote(self.contact, self.owner)
        self.assertRejected(
            lambda: Photo.objects.create(image="x.jpg", job=j, quote=q, uploaded_by=self.owner)
        )

    def test_one_primary_property_per_contact(self):
        Property.objects.create(
            contact=self.contact,
            street="1 A St",
            city="X",
            state="NY",
            postal_code="1",
            is_primary=True,
        )
        self.assertRejected(
            lambda: Property.objects.create(
                contact=self.contact,
                street="2 B St",
                city="X",
                state="NY",
                postal_code="1",
                is_primary=True,
            )
        )


class FollowUpTaskConstraintTests(TestCase):
    def setUp(self):
        self.owner = f.user()
        self.contact = f.contact(self.owner)
        self.gutters = f.service()

    def _follow_up(self, **extra):
        return Task.objects.create(
            kind=Task.Kind.FOLLOW_UP,
            title="Due for gutters",
            assigned_to=self.owner,
            created_by=self.owner,
            contact=extra.pop("contact", self.contact),
            service_type=extra.pop("service_type", self.gutters),
            **extra,
        )

    def test_follow_up_requires_contact_and_service(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._follow_up(service_type=None)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._follow_up(contact=None)

    def test_only_one_open_follow_up_per_contact_and_service(self):
        self._follow_up()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._follow_up()

    def test_completed_follow_up_does_not_block_the_next(self):
        self._follow_up(status=Task.Status.COMPLETED)
        self._follow_up()  # no error
        self.assertEqual(Task.objects.filter(kind=Task.Kind.FOLLOW_UP).count(), 2)


class UploadNamingTests(TestCase):
    """Stored file names never reuse the uploader's filename, which can
    carry names or addresses ("smith_house.jpg")."""

    def test_photo_named_by_uuid_under_private(self):
        photo = Photo()
        path = photo_upload_to(photo, "Smith House.JPG")
        self.assertEqual(path, f"private/photos/{photo.uuid}.jpg")

    def test_unknown_photo_suffix_normalized(self):
        self.assertTrue(photo_upload_to(Photo(), "evil.php").endswith(".jpg"))

    def test_avatar_random_name_under_private(self):
        path = avatar_upload_to(None, "Jane Doe.png")
        self.assertRegex(path, r"^private/avatars/[0-9a-f]{32}\.png$")
