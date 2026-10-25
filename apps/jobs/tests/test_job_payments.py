"""Money received against a job (ADR 0013).

This business is paid before the work is finished, so a payment
normally has no invoice at all. Before this, `Payment.invoice` was
required and the only way in was an invoice page — so there was
nowhere to record the money.

The test that matters most here is
`test_a_payment_with_no_invoice_is_counted_as_collected`. Making the
column nullable put a NULL on the far side of
`summary()`'s `.exclude(invoice__status=VOID)`, and a filter across a
nullable foreign key is exactly where rows vanish quietly: with the
column still `NOT NULL` that exclude compiled to an INNER JOIN, which
would have dropped every job payment from the Financials "collected"
figure. Django widens it to a LEFT JOIN with an `IS NOT NULL` guard
once the field is nullable, so it is correct — and this test is what
holds it there, because nothing on a rendered page would show the
difference.
"""

import importlib
from datetime import date
from decimal import Decimal

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import migrations
from django.test import TestCase
from django.urls import reverse

from apps.crm.tests._helpers import grant_role
from apps.jobs import reports
from apps.jobs.models import Invoice, Payment
from apps.users.roles import Role

from . import _factories as f

migration = importlib.import_module("apps.jobs.migrations.0006_payment_belongs_to_the_job")

PASSWORD = "correct-horse-battery"
TODAY = date(2026, 9, 29)


class JobPaymentTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.crew = grant_role(f.user("casey"), Role.CLEANER)
        self.customer = f.contact(self.owner)
        self.job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("200"))])
        self.url = reverse("jobs:job_payment_create", args=[self.job.pk])
        self.client.login(username="boss", password=PASSWORD)

    def form(self, **extra):
        data = {
            "amount": "200",
            "received_on": "2026-09-20",
            "method": Payment.Method.CARD,
            "notes": "",
        }
        data.update(extra)
        return data

    def test_a_payment_can_be_recorded_against_a_job_with_no_invoice(self):
        response = self.client.post(self.url, self.form())
        self.assertRedirects(response, self.job.get_absolute_url())
        payment = Payment.objects.get()
        self.assertEqual(payment.job, self.job)
        self.assertIsNone(payment.invoice, "no invoice is the normal case here")
        self.assertEqual(payment.recorded_by, self.owner)

    def test_the_form_starts_at_what_is_left_to_pay(self):
        """After a part payment, which is the half that has teeth.

        The first version only looked at a job with nothing paid yet,
        where the remaining balance and the full value are the same
        number — so it passed with `paid` hard-wired to zero. Found by
        mutating `JobQuerySet.with_balances` to ignore payments
        entirely and watching nothing fail.
        """
        self.assertEqual(
            self.client.get(self.url).context["form"].initial["amount"], Decimal("200.00")
        )
        self.client.post(self.url, self.form(amount="50"))
        response = self.client.get(self.url)
        self.assertEqual(response.context["form"].initial["amount"], Decimal("150.00"))
        self.assertContains(response, "J-")
        self.assertContains(response, "Job total")

    def test_the_job_page_shows_what_is_paid_and_what_is_left(self):
        self.client.post(self.url, self.form(amount="150"))
        response = self.client.get(self.job.get_absolute_url())
        self.assertEqual(response.context["paid"], Decimal("150"))
        self.assertEqual(response.context["balance"], Decimal("50"))
        self.assertContains(response, "outstanding")

    def test_paying_the_rest_leaves_nothing_outstanding(self):
        self.client.post(self.url, self.form(amount="200"))
        response = self.client.get(self.job.get_absolute_url())
        self.assertEqual(response.context["balance"], Decimal("0"))
        self.assertContains(response, "Paid in full")

    def test_overpaying_is_allowed_and_said_out_loud(self):
        response = self.client.post(self.url, self.form(amount="250"), follow=True)
        self.assertEqual(Payment.objects.get().amount, Decimal("250"))
        self.assertIn(
            "more than the balance",
            " ".join(str(m) for m in response.context["messages"]),
        )

    def test_a_payment_with_no_invoice_is_counted_as_collected(self):
        """The one that would otherwise fail silently.

        `summary()` excludes payments against a void invoice. A
        payment with **no** invoice must survive that exclusion, or
        the Financials "collected" figure ignores every payment this
        business actually takes. Nothing on screen would say so.
        """
        self.client.post(self.url, self.form(amount="200", received_on="2026-09-20"))
        period = reports.report_period("month", None, None, TODAY)[0]
        self.assertEqual(reports.summary(period)["collected"], Decimal("200"))

    def test_a_payment_against_a_void_invoice_is_still_excluded(self):
        """The other half: widening the filter must not have widened it
        so far that voided money counts again."""
        voided = f.invoice(
            self.job,
            lines=[(Decimal("1"), Decimal("70"))],
            issued=date(2026, 9, 4),
            status=Invoice.Status.VOID,
        )
        Payment.objects.create(
            job=self.job,
            invoice=voided,
            amount=Decimal("70"),
            received_on=date(2026, 9, 20),
            recorded_by=self.owner,
        )
        self.client.post(self.url, self.form(amount="200", received_on="2026-09-20"))
        period = reports.report_period("month", None, None, TODAY)[0]
        self.assertEqual(reports.summary(period)["collected"], Decimal("200"))

    def test_a_payment_through_the_invoice_route_also_names_the_job(self):
        """Otherwise money taken the old way is invisible to every
        job-based figure — and `job` is required, so it would simply
        fail to save."""
        invoice = f.invoice(
            self.job, lines=[(Decimal("1"), Decimal("200"))], issued=date(2026, 9, 3)
        )
        response = self.client.post(
            reverse("jobs:payment_create", args=[invoice.pk]), self.form(amount="200")
        )
        self.assertRedirects(response, invoice.get_absolute_url())
        payment = Payment.objects.get()
        self.assertEqual((payment.invoice, payment.job), (invoice, self.job))

    def test_a_payment_cannot_name_an_invoice_for_a_different_job(self):
        other = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("50"))])
        invoice = f.invoice(other, lines=[(Decimal("1"), Decimal("50"))])
        payment = Payment(
            job=self.job,
            invoice=invoice,
            amount=Decimal("50"),
            received_on=date(2026, 9, 20),
            recorded_by=self.owner,
        )
        with self.assertRaises(ValidationError) as caught:
            payment.full_clean()
        self.assertIn("invoice", caught.exception.message_dict)

    def test_only_the_owner_can_record_a_payment(self):
        for username in ("rep", "casey"):
            self.client.login(username=username, password=PASSWORD)
            self.assertEqual(self.client.get(self.url).status_code, 403, username)
            self.assertEqual(self.client.post(self.url, self.form()).status_code, 403, username)
        self.assertFalse(Payment.objects.exists())

    def test_a_payment_with_no_invoice_can_be_stringified(self):
        """`__str__` read `self.invoice.number` straight through, so
        anything that printed a job payment — the admin, the change
        log — raised AttributeError."""
        self.client.post(self.url, self.form())
        payment = Payment.objects.get()
        self.assertIn(self.job.number, str(payment))

    def test_a_mismatched_pair_is_refused_on_an_ordinary_save(self):
        """`clean()` only runs through forms. An ordinary `save()` of a
        job and an invoice for different jobs would have counted the
        same money toward one job in the job balances and another in
        the invoice's."""
        other = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("50"))])
        invoice = f.invoice(other, lines=[(Decimal("1"), Decimal("50"))])
        with self.assertRaises(ValueError):
            Payment.objects.create(
                job=self.job,
                invoice=invoice,
                amount=Decimal("50"),
                received_on=date(2026, 9, 20),
                recorded_by=self.owner,
            )
        self.assertFalse(Payment.objects.exists())

    def test_overpaying_says_by_how_much_on_the_job(self):
        """The balance goes negative, and the page used to show only
        "Paid in full" — hiding the figure while a comment beside it
        claimed otherwise."""
        self.client.post(self.url, self.form(amount="250"))
        response = self.client.get(self.job.get_absolute_url())
        self.assertEqual(response.context["balance"], Decimal("-50"))
        self.assertContains(response, "Overpaid by")
        self.assertNotContains(response, "Paid in full")

    def test_an_invoice_raised_later_says_the_job_was_already_paid(self):
        """The foot-gun: pay on the job, invoice afterwards, and the
        invoice counts none of it. Without a word on the page that is
        an invitation to bill the customer twice.

        Also pins that `exclude(invoice=...)` keeps the payments whose
        invoice is NULL — the same nullable-join trap as `collected`,
        in a second place.
        """
        self.client.post(self.url, self.form(amount="200"))
        invoice = f.invoice(
            self.job, lines=[(Decimal("1"), Decimal("200"))], issued=date(2026, 9, 3)
        )
        response = self.client.get(invoice.get_absolute_url())
        self.assertEqual(response.context["paid_on_the_job"], Decimal("200"))
        self.assertContains(response, "already been received")
        self.assertContains(response, "before chasing payment")

    def test_a_payment_against_this_invoice_is_not_counted_as_elsewhere(self):
        """The other half, or the note would appear on every invoice
        that has ever been paid."""
        invoice = f.invoice(
            self.job, lines=[(Decimal("1"), Decimal("200"))], issued=date(2026, 9, 3)
        )
        self.client.post(reverse("jobs:payment_create", args=[invoice.pk]), self.form())
        response = self.client.get(invoice.get_absolute_url())
        self.assertEqual(response.context["paid_on_the_job"], Decimal("0"))
        self.assertNotContains(response, "already been received")

    def test_nothing_is_saved_when_the_audit_write_fails(self):
        """Money is the one place a half-written pair is worse than no
        write: the request fails, the owner records it again, and it is
        in twice."""
        from unittest import mock

        with mock.patch("apps.crm.audit.record", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.form())
        self.assertFalse(Payment.objects.exists())

    def test_reversing_the_migration_refuses_rather_than_losing_money(self):
        """The reverse makes `Payment.invoice` NOT NULL again, which a
        job-only payment cannot satisfy.

        The two ways to make a rollback succeed would be to invent an
        invoice or to delete the payment, and neither is a decision a
        migration should take on its own. Called directly, the way
        `test_migrations.py` exercises the Phase 17 functions.
        """
        self.client.post(self.url, self.form())
        with self.assertRaises(RuntimeError) as caught:
            migration.refuse_if_payments_have_no_invoice(django_apps, None)
        message = str(caught.exception)
        self.assertIn("cannot represent", message)
        self.assertIn("1 payment", message)
        self.assertTrue(Payment.objects.exists(), "it must not delete anything")

    def test_the_reverse_guard_is_wired_into_the_migration(self):
        """Calling the function directly says nothing about whether
        the migration uses it.

        Mutating the operation back to `RunPython.noop` left every
        other test here green — the guard would simply never run on a
        real rollback. So this asserts the wiring, not the behaviour.
        """
        run_python = next(
            op for op in migration.Migration.operations if isinstance(op, migrations.RunPython)
        )
        self.assertIs(run_python.code, migration.fill_job_from_invoice)
        self.assertIs(run_python.reverse_code, migration.refuse_if_payments_have_no_invoice)

    def test_reversing_is_fine_while_every_payment_has_an_invoice(self):
        invoice = f.invoice(self.job, lines=[(Decimal("1"), Decimal("200"))])
        self.client.post(reverse("jobs:payment_create", args=[invoice.pk]), self.form())
        migration.refuse_if_payments_have_no_invoice(django_apps, None)  # does not raise

    def test_the_payment_list_names_the_job(self):
        self.client.post(self.url, self.form())
        response = self.client.get(reverse("jobs:payment_list"))
        self.assertContains(response, self.job.number)
        self.assertContains(response, self.job.get_absolute_url())
