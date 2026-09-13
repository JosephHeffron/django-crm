"""Seed the "Staff" group with the add/change permissions day-to-day
CRM users need. See docs/PERMISSIONS.md for the full design and the
reasoning behind calling create_permissions() explicitly here.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

STAFF_PERMISSIONS = [
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


def create_staff_group(apps, schema_editor):
    # Model permissions are normally created by a post_migrate signal
    # that fires once, after every migration in this run has already
    # applied — including this one. On a fresh install that signal
    # hasn't fired yet when this function runs, so the permissions
    # this migration needs wouldn't exist yet. Create them explicitly
    # first, the same way Django's own documentation recommends for
    # exactly this "seed a group in a migration" scenario.
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    group, _ = Group.objects.get_or_create(name="Staff")
    permissions = []
    for app_label, codename in STAFF_PERMISSIONS:
        content_type = ContentType.objects.get(app_label=app_label, model=codename.split("_", 1)[1])
        permissions.append(Permission.objects.get(content_type=content_type, codename=codename))
    group.permissions.set(permissions)


def remove_staff_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name="Staff").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0004_auditlogentry"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(create_staff_group, remove_staff_group),
    ]
