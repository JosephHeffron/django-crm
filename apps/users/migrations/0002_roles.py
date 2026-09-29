"""Seed the Owner / Sales Rep / Cleaner role groups and retire "Staff".

docs/decisions/0008-roles-and-row-level-scoping.md. Owner and Sales Rep
inherit exactly the add/change permissions crm's 0005 migration gave
"Staff"; Cleaner gets none (Cleaners never write CRM customer records).
Existing Staff members become Sales Reps — Staff was the day-to-day
sales-user tier. Fully reversible: the reverse restores Staff with its
permissions and members.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

# Kept identical to crm/0005's STAFF_PERMISSIONS (migrations can't
# safely import each other's module-level constants).
SALES_PERMISSIONS = [
    ("crm", "add_company"),
    ("crm", "change_company"),
    ("crm", "add_contact"),
    ("crm", "change_contact"),
    ("crm", "add_lead"),
    ("crm", "change_lead"),
    ("crm", "add_deal"),
    ("crm", "change_deal"),
    ("crm", "add_task"),
    ("crm", "change_task"),
    ("crm", "add_activity"),
]

OWNER, SALES_REP, CLEANER = "Owner", "Sales Rep", "Cleaner"


def _permissions(apps, codes):
    # Same reasoning as crm/0005: on a fresh install the post_migrate
    # signal that creates model permissions hasn't fired yet.
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    perms = []
    for app_label, codename in codes:
        ct = ContentType.objects.get(app_label=app_label, model=codename.split("_", 1)[1])
        perms.append(Permission.objects.get(content_type=ct, codename=codename))
    return perms


def create_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    perms = _permissions(apps, SALES_PERMISSIONS)

    owner, _ = Group.objects.get_or_create(name=OWNER)
    sales, _ = Group.objects.get_or_create(name=SALES_REP)
    Group.objects.get_or_create(name=CLEANER)
    owner.permissions.set(perms)
    sales.permissions.set(perms)

    staff = Group.objects.filter(name="Staff").first()
    if staff is not None:
        for user in staff.user_set.all():
            user.groups.add(sales)
        staff.delete()


def restore_staff(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    staff, _ = Group.objects.get_or_create(name="Staff")
    staff.permissions.set(_permissions(apps, SALES_PERMISSIONS))
    sales = Group.objects.filter(name=SALES_REP).first()
    if sales is not None:
        for user in sales.user_set.all():
            user.groups.add(staff)
    Group.objects.filter(name__in=[OWNER, SALES_REP, CLEANER]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
        ("crm", "0005_seed_staff_group"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(create_roles, restore_staff)]
