"""A payment belongs to a job (ADR 0013).

Written by hand rather than generated, because a required foreign key
cannot be added to a table that already has rows in one step. The
three-step dance is: add it nullable, fill it in, then tighten it.

Every existing payment reaches a job through its invoice
(`Invoice.job` is required), so nothing is orphaned and nothing is
guessed. Measured before writing this: 93 payments, 93 with an
invoice, 0 without.

Reversible. The reverse drops the column, so the data step's reverse
is a no-op — there is nothing to put back.
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
        migrations.RunPython(fill_job_from_invoice, migrations.RunPython.noop),
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
