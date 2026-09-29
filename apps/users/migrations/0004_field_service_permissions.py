"""Model permissions for the field-service models, per role
(docs/PERMISSIONS.md). Additive: the reverse removes exactly these.

Roles decide which *pages* someone can use; these decide which writes
succeed within them (defense in depth, ADR 0008). Row-level rules —
a cleaner may only update jobs they're assigned to — live in views.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

ADD_CHANGE = ("add", "change")
ADD_CHANGE_DELETE = ("add", "change", "delete")

OWNER = {
    "crm": {
        "tag": ADD_CHANGE_DELETE,
        "property": ADD_CHANGE_DELETE,
        "note": ADD_CHANGE_DELETE,
        "businessplan": ADD_CHANGE_DELETE,
        "planchecklistitem": ADD_CHANGE_DELETE,
    },
    "jobs": {
        "servicetype": ADD_CHANGE,
        "quote": ADD_CHANGE,
        "quotelineitem": ADD_CHANGE_DELETE,
        "job": ADD_CHANGE,
        "joblineitem": ADD_CHANGE_DELETE,
        "jobassignment": ADD_CHANGE_DELETE,
        "photo": ADD_CHANGE_DELETE,
        "invoice": ADD_CHANGE,
        "invoicelineitem": ADD_CHANGE_DELETE,
        "payment": ADD_CHANGE,
        "expense": ADD_CHANGE_DELETE,
    },
    "messaging": {
        "channel": ADD_CHANGE,
        "channelmembership": ADD_CHANGE_DELETE,
        "message": ADD_CHANGE,
    },
}

SALES_REP = {
    "crm": {
        "tag": ("add",),
        "property": ADD_CHANGE,
        "note": ADD_CHANGE,
        "businessplan": ADD_CHANGE,
        "planchecklistitem": ADD_CHANGE_DELETE,
    },
    "jobs": {
        "quote": ADD_CHANGE,
        "quotelineitem": ADD_CHANGE_DELETE,
        "job": ADD_CHANGE,
        "joblineitem": ADD_CHANGE_DELETE,
        "jobassignment": ADD_CHANGE_DELETE,
        "photo": ("add",),
    },
    "messaging": {"message": ("add",), "channelmembership": ADD_CHANGE},
}

# Crews update their own jobs (status, hours) and add photos/notes —
# which jobs is enforced row-by-row in the views, not here.
CLEANER = {
    "crm": {"note": ("add",)},
    "jobs": {"job": ("change",), "jobassignment": ("change",), "photo": ("add",)},
    "messaging": {"message": ("add",), "channelmembership": ADD_CHANGE},
}

GRANTS = {"Owner": OWNER, "Sales Rep": SALES_REP, "Cleaner": CLEANER}


def _permissions(apps, spec):
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    for app_label, models in spec.items():
        for model, actions in models.items():
            ct = ContentType.objects.get(app_label=app_label, model=model)
            for action in actions:
                yield Permission.objects.get(content_type=ct, codename=f"{action}_{model}")


def grant(apps, schema_editor):
    # See crm/0005: permissions don't exist yet on a fresh install.
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    Group = apps.get_model("auth", "Group")
    for group_name, spec in GRANTS.items():
        Group.objects.get(name=group_name).permissions.add(*_permissions(apps, spec))


def revoke(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for group_name, spec in GRANTS.items():
        group = Group.objects.filter(name=group_name).first()
        if group is not None:
            group.permissions.remove(*_permissions(apps, spec))


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0003_userprofile_photo"),
        ("jobs", "0001_initial"),
        ("messaging", "0001_initial"),
        ("crm", "0007_field_service_task_links"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
