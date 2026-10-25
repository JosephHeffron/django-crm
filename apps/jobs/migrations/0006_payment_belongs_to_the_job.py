"""A payment belongs to a job (ADR 0013).

Written by hand rather than generated, because a required foreign key
cannot be added to a table that already has rows in one step. The
three-step dance is: add it nullable, fill it in, then tighten it.

Every existing payment reaches a job through its invoice
(`Invoice.job` is required), so nothing is orphaned and nothing is
guessed. Measured before writing this: 93 payments, 93 with an
invoice, 0 without.

**Reversible only until the first job-only payment is taken.** The
reverse restores `Payment.invoice` to NOT NULL, and a payment recorded
against a job with no invoice cannot be expressed in the old schema at
all. Rather than let PostgreSQL refuse it with a message about a
constraint, or — far worse — delete the rows to make the rollback
succeed, the reverse data step counts them and explains. An earlier
version of this docstring simply claimed "reversible", which was true
only on the day it was written.
"""

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def fill_job_from_invoice(apps, schema_editor):
    Payment = apps.get_model("jobs", "Payment")
    Invoice = apps.get_model("jobs", "Invoice")
    Payment.objects.filter(job__isnull=True).update(
        job_id=Subquery(Invoice.objects.filter(pk=OuterRef("invoice_id")).values("job_id")[:1])
    )
    stranded = Payment.objects.filter(job__isnull=True).count()
    if stranded:
        # The AlterField below would fail anyway, with a message about
        # a not-null constraint that says nothing about why. Fail here
        # instead, where the reason can be stated.
        raise RuntimeError(
            f"{stranded} payment(s) have no invoice to take a job from, so this migration "
            "cannot fill Payment.job for them. Give each one a job (or delete it) and run "
            "the migration again."
        )


def refuse_if_payments_have_no_invoice(apps, schema_editor):
    """The reverse of the step above.

    Going back means `Payment.invoice` becomes NOT NULL again, which a
    job-only payment cannot satisfy. Nothing here invents an invoice
    and nothing deletes a payment — money is not something a rollback
    should quietly destroy — so this stops with an explanation and
    leaves the decision to a person.
    """
    Payment = apps.get_model("jobs", "Payment")
    stranded = Payment.objects.filter(invoice__isnull=True).count()
    if stranded:
        raise RuntimeError(
            f"{stranded} payment(s) were recorded against a job with no invoice, which the "
            "schema before this migration cannot represent. Reversing would mean either "
            "inventing an invoice for each or deleting the payment, and neither is a "
            "decision a migration should make. Resolve them first (invoice the work, or "
            "remove the payments deliberately), then reverse."
        )


class Migration(migrations.Migration):
    dependencies = [("jobs", "0005_job_completed_at_index")]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="job",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="jobs.job",
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="invoice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="jobs.invoice",
            ),
        ),
        migrations.RunPython(fill_job_from_invoice, refuse_if_payments_have_no_invoice),
        migrations.AlterField(
            model_name="payment",
            name="job",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="jobs.job",
            ),
        ),
    ]
