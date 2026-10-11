"""Money and hours, at the places rounding can make them disagree.

QA audit. A CRM's worst defects are not crashes — they are figures that
are wrong but plausible, because nothing complains and the owner bills
from them. These tests go after that class specifically:

- a line total is `quantity` (2dp) × `unit_price` (2dp), so it can carry
  **four** decimal places. Everything downstream — document totals,
  invoice balances, "is this paid" — inherits that.
- hours are a duration divided by 3600, which almost never lands on a
  whole cent of an hour.

Where the code is right, these pin it so a later refactor cannot
quietly break it. Where it is not, they say so.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.tests._helpers import grant_role
from apps.jobs import crew
from apps.jobs.models import Invoice, Payment, Quote, QuoteLineItem, TimeEntry
from apps.users.models import get_profile
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"


class LineTotalPrecisionTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.customer = f.contact(self.owner)
        self.service = f.service()

    def quote_with(self, lines):
        quote = Quote.objects.create(contact=self.customer, prepared_by=self.owner)
        for position, (quantity, price) in enumerate(lines):
            QuoteLineItem.objects.create(
                quote=quote,
                service_type=self.service,
                description="work",
                quantity=Decimal(quantity),
                unit_price=Decimal(price),
                position=position,
            )
        return quote

    def test_a_single_line_can_carry_four_decimal_places(self):
        """Not a defect — the arithmetic is exact, which is the right
        choice. This pins the fact so the tests below are read correctly.
        """
        quote = self.quote_with([("2.33", "19.99")])
        self.assertEqual(quote.total, Decimal("46.5767"))

    def test_the_aggregate_and_the_annotation_agree(self):
        """Two code paths compute the same number.

        `TotalMixin.total` uses the `with_totals()` annotation when one
        is present and a fresh aggregate otherwise. A list page and a
        detail page therefore reach the total differently, and a
        customer who saw one figure in a list and another on the page
        would be right to distrust both.
        """
        quote = self.quote_with([("2.33", "19.99"), ("0.17", "3.33"), ("1.01", "0.07")])
        annotated = Quote.objects.with_totals().get(pk=quote.pk)
        self.assertEqual(annotated.total, Quote.objects.get(pk=quote.pk).total)

    def test_the_total_is_the_sum_of_the_lines_not_a_sum_of_roundings(self):
        """Rounding each line and then adding gives a different answer
        from adding and then rounding. The document must do the latter.
        """
        lines = [("0.33", "0.05"), ("0.33", "0.05"), ("0.33", "0.05")]
        quote = self.quote_with(lines)
        exact = sum(Decimal(q) * Decimal(p) for q, p in lines)
        self.assertEqual(quote.total, exact)
        rounded_first = sum((Decimal(q) * Decimal(p)).quantize(Decimal("0.01")) for q, p in lines)
        self.assertNotEqual(exact, rounded_first)

    def test_an_empty_document_totals_zero_rather_than_none(self):
        """`Coalesce` earns its place: `None` would propagate into every
        balance and comparison downstream."""
        quote = Quote.objects.create(contact=self.customer, prepared_by=self.owner)
        self.assertEqual(quote.total, Decimal("0.00"))
        self.assertEqual(Quote.objects.with_totals().get(pk=quote.pk).total, Decimal("0.00"))

    def test_totals_do_not_multiply_when_several_sums_are_annotated(self):
        """The bug `_sum_subquery` exists to prevent.

        Annotating two sums as JOINs multiplies the rows into each
        other, inflating both. Two lines and two payments is the
        smallest case that would show it.
        """
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("100"))])
        invoice = f.invoice(
            job, lines=[(Decimal("1"), Decimal("60")), (Decimal("1"), Decimal("40"))]
        )
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal("10.00"),
            received_on=timezone.localdate(),
            recorded_by=self.owner,
        )
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal("15.00"),
            received_on=timezone.localdate(),
            recorded_by=self.owner,
        )
        annotated = Invoice.objects.with_balances().get(pk=invoice.pk)
        self.assertEqual(annotated.total, Decimal("100"))
        self.assertEqual(annotated.paid, Decimal("25.00"))
        self.assertEqual(annotated.balance, Decimal("75.00"))


class PaidInFullTests(TestCase):
    """The question that matters to a business: has this been paid?"""

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.customer = f.contact(self.owner)
        self.service = f.service()
        self.job = f.job(self.customer, self.owner, lines=[])

    def invoice_for(self, quantity, price):
        return f.invoice(self.job, lines=[(Decimal(quantity), Decimal(price))])

    def test_paying_the_rounded_amount_settles_a_fractional_invoice(self):
        """A customer cannot pay 46.5767. They pay 46.58.

        If `payment_status` demanded an exact match, every invoice with
        a fractional total would sit "overdue" for ever. It compares
        `balance <= 0`, which is what makes a real payment work — pinned
        here because a later tightening to `== 0` would look harmless.
        """
        invoice = self.invoice_for("2.33", "19.99")
        self.assertEqual(invoice.total, Decimal("46.5767"))
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal("46.58"),
            received_on=timezone.localdate(),
            recorded_by=self.owner,
        )
        self.assertLessEqual(invoice.balance, Decimal("0"))
        self.assertEqual(invoice.payment_status(timezone.localdate()), "paid")

    def test_underpaying_by_a_cent_does_not_read_as_paid(self):
        """The other side: `<= 0` must not be so loose that a short
        payment closes the invoice."""
        invoice = self.invoice_for("1", "100.00")
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal("99.99"),
            received_on=timezone.localdate(),
            recorded_by=self.owner,
        )
        self.assertEqual(invoice.balance, Decimal("0.01"))
        self.assertNotEqual(invoice.payment_status(timezone.localdate()), "paid")

    def test_overpaying_does_not_produce_a_negative_amount_due(self):
        """A credit is a real situation; showing a negative "amount due"
        on a statement is not. This records what the code does today so
        a decision about credits is a deliberate one.
        """
        invoice = self.invoice_for("1", "50.00")
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal("60.00"),
            received_on=timezone.localdate(),
            recorded_by=self.owner,
        )
        self.assertEqual(invoice.balance, Decimal("-10.00"))
        self.assertEqual(invoice.payment_status(timezone.localdate()), "paid")


class HoursTests(TestCase):
    """Hours feed pay, so where they are rounded matters."""

    def setUp(self):
        self.casey = grant_role(f.user("casey"), Role.CLEANER)
        self.monday = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0)

    def clock(self, minutes, day_offset=0):
        start = self.monday + timedelta(days=day_offset)
        return TimeEntry.objects.create(
            user=self.casey, started_at=start, ended_at=start + timedelta(minutes=minutes)
        )

    def test_the_period_total_sums_durations_before_rounding(self):
        """The correct order, and the reason payroll is right.

        Three ten-minute stretches are half an hour. Rounding each one
        first gives 0.51, which would be wrong on a payslip.
        """
        for i in range(3):
            self.clock(10, day_offset=i)
        total = crew.hours_in_period(TimeEntry.objects.filter(user=self.casey))
        self.assertEqual(total, Decimal("0.50"))

    def test_pay_is_computed_from_the_unrounded_period_total(self):
        profile = get_profile(self.casey)
        profile.hourly_rate = Decimal("30.00")
        profile.save(update_fields=["hourly_rate"])
        for i in range(3):
            self.clock(10, day_offset=i)
        today = timezone.localdate()
        row = crew.payroll([self.casey], today - timedelta(days=7), today + timedelta(days=7))[0]
        self.assertEqual(row["hours"], Decimal("0.50"))
        self.assertEqual(row["pay"], Decimal("15.00"))

    def test_a_missing_rate_reports_no_pay_rather_than_guessing_zero(self):
        self.clock(60)
        today = timezone.localdate()
        row = crew.payroll([self.casey], today - timedelta(days=7), today + timedelta(days=7))[0]
        self.assertIsNone(row["rate"])
        self.assertIsNone(row["pay"])

    def test_a_running_clock_has_no_length_yet(self):
        entry = TimeEntry.objects.create(user=self.casey, started_at=self.monday)
        self.assertIsNone(entry.hours)
        self.assertTrue(entry.is_running)

    def test_a_running_clock_is_left_out_of_the_period_total(self):
        self.clock(60)
        TimeEntry.objects.create(user=self.casey, started_at=self.monday + timedelta(days=1))
        today = timezone.localdate()
        row = crew.payroll([self.casey], today - timedelta(days=7), today + timedelta(days=7))[0]
        self.assertEqual(row["hours"], Decimal("1.00"))

    def test_the_timesheet_rows_do_not_always_add_up_to_its_own_total(self):
        """QA-002, recorded rather than fixed — see `docs/BUG_LOG.md`.

        `time_clock.html` prints `entry.hours` per row, each rounded on
        its own, under a `<tfoot>` labelled Total that holds
        `week_hours`, rounded once from the summed durations. The total
        is the authoritative one: it is what pay is computed from. But
        the column above it does not add up to it.

        Three ten-minute stretches show as 0.17, 0.17, 0.17 over a total
        of 0.50. Nothing is miscalculated and nobody is mispaid; the
        page just invites a crew member to distrust a figure that is
        correct.

        Every available fix trades this for something worse — summing
        the displayed values would put rounding drift into pay, and
        re-spreading the residue across rows would print hours against a
        stretch that the person did not work — so this is a
        characterization test. It fails if someone changes the
        behaviour, which makes that a decision rather than an accident.
        """
        entries = [self.clock(10, day_offset=i) for i in range(3)]
        rows = [entry.hours for entry in entries]
        total = crew.hours_in_period(TimeEntry.objects.filter(user=self.casey))
        self.assertEqual(rows, [Decimal("0.17")] * 3)
        self.assertEqual(total, Decimal("0.50"))
        self.assertNotEqual(sum(rows), total)

    def test_the_timesheet_page_really_does_show_both_figures(self):
        """Without this, the test above is a claim about a template
        nobody checked."""
        self.client.login(username="casey", password=PASSWORD)
        self.clock(10)
        response = self.client.get(reverse("jobs:time_clock"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Total", body)
        self.assertIn("0.17", body)
