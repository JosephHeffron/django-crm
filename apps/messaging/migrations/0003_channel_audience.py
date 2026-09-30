"""Who may read a public channel: everyone, or the Owner and sales reps.
#sales becomes sales-only — quotes and pricing talk isn't crew business
(Phase 17 unit 3d)."""

from django.db import migrations, models


def restrict_sales(apps, schema_editor):
    Channel = apps.get_model("messaging", "Channel")
    Channel.objects.filter(slug="sales", kind="public").update(audience="sales")


class Migration(migrations.Migration):
    dependencies = [("messaging", "0002_default_channels")]

    operations = [
        migrations.AddField(
            model_name="channel",
            name="audience",
            field=models.CharField(
                choices=[("everyone", "Everyone"), ("sales", "Owner and sales reps")],
                default="everyone",
                max_length=10,
            ),
        ),
        # Reversing drops the column, which removes the setting with it.
        migrations.RunPython(restrict_sales, migrations.RunPython.noop),
    ]
