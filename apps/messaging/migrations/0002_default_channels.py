"""The three team channels every install starts with (reference data)."""

from django.db import migrations

CHANNELS = [
    ("general", "general", "Company-wide announcements and chatter"),
    ("crew", "crew", "Field crews: schedules, access notes, supplies"),
    ("sales", "sales", "Quotes, leads, and follow-ups"),
]


def create(apps, schema_editor):
    Channel = apps.get_model("messaging", "Channel")
    for name, slug, topic in CHANNELS:
        Channel.objects.get_or_create(
            slug=slug, defaults={"name": name, "topic": topic, "kind": "public"}
        )


def remove(apps, schema_editor):
    # Memberships (read markers) are cleared; the channels themselves are
    # deleted by primary key rather than through Django's deletion
    # collector (see jobs/0003's _delete_by_pk), so a channel that
    # already holds messages makes PostgreSQL refuse the reverse instead
    # of silently discarding conversation history.
    Channel = apps.get_model("messaging", "Channel")
    ChannelMembership = apps.get_model("messaging", "ChannelMembership")
    pks = list(
        Channel.objects.filter(slug__in=[c[1] for c in CHANNELS]).values_list("pk", flat=True)
    )
    ChannelMembership.objects.filter(channel_id__in=pks).delete()
    if pks:
        table = schema_editor.quote_name(Channel._meta.db_table)
        schema_editor.execute(f"DELETE FROM {table} WHERE id = ANY(%s)", [pks])


class Migration(migrations.Migration):
    dependencies = [("messaging", "0001_initial")]

    operations = [migrations.RunPython(create, remove)]
