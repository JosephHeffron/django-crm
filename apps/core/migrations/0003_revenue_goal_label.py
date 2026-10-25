"""The revenue goal's label, nothing else.

A choices label lives in the migration state as well as the model, so
changing "Revenue invoiced" to "Revenue earned" needs this file. The
stored value is still `revenue`, so no row changes and no data moves —
ADR 0013 changed what the figure counts, and this changes what it is
called.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_goal_notification"),
    ]

    operations = [
        migrations.AlterField(
            model_name="goal",
            name="metric",
            field=models.CharField(
                choices=[
                    ("revenue", "Revenue earned"),
                    ("jobs", "Jobs completed"),
                    ("customers", "New customers"),
                ],
                max_length=10,
                unique=True,
            ),
        ),
    ]
