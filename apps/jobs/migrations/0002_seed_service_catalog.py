"""Seed the default service catalog — reference data every install needs
(not demo data, so it lives here rather than in seed_demo). Prices and
follow-up intervals are starting defaults; the Owner edits them.
"""

from decimal import Decimal

from django.db import migrations

# (name, slug, default_price, pricing_unit, followup_interval_months, tone)
SERVICES = [
    ("Window Washing — Exterior", "window-washing-exterior", "8.00", "window", 6, 1),
    ("Window Washing — Interior", "window-washing-interior", "6.00", "window", 6, 6),
    ("Gutter Cleaning", "gutter-cleaning", "175.00", "flat", 6, 2),
    ("Pressure Washing", "pressure-washing", "0.35", "sq_ft", 12, 5),
    ("Siding Cleaning", "siding-cleaning", "300.00", "flat", 12, 9),
    ("Weed Removal", "weed-removal", "55.00", "hour", 3, 10),
    ("Tree Removal", "tree-removal", "650.00", "flat", None, 7),
    ("Mulching", "mulching", "85.00", "item", 12, 3),
    ("Trimming", "trimming", "60.00", "hour", 6, 8),
    ("Other", "other", "0.00", "flat", None, 4),
]


def seed(apps, schema_editor):
    ServiceType = apps.get_model("jobs", "ServiceType")
    for position, (name, slug, price, unit, interval, tone) in enumerate(SERVICES):
        ServiceType.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "default_price": Decimal(price),
                "pricing_unit": unit,
                "followup_interval_months": interval,
                "tone": tone,
                "position": position,
            },
        )


def unseed(apps, schema_editor):
    # Deleted by primary key, not through Django's deletion collector,
    # which can fail in multi-app backwards migrations (see
    # jobs/0003's _delete_by_pk). PostgreSQL's FK constraints refuse the
    # delete if any quote, job, invoice, or task still uses a service —
    # reversing this is only meaningful before the catalog is in use.
    ServiceType = apps.get_model("jobs", "ServiceType")
    pks = list(
        ServiceType.objects.filter(slug__in=[s[1] for s in SERVICES]).values_list("pk", flat=True)
    )
    if pks:
        table = schema_editor.quote_name(ServiceType._meta.db_table)
        schema_editor.execute(f"DELETE FROM {table} WHERE id = ANY(%s)", [pks])


class Migration(migrations.Migration):
    dependencies = [("jobs", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
