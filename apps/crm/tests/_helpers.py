"""Shared test helpers — not itself a test module (leading underscore
keeps Django's test*.py discovery from picking it up).
"""

from django.contrib.auth.models import Group


def grant_staff(user):
    """Add user to the "Staff" group (seeded by crm's 0005 migration),
    granting the add/change permissions most view tests exercise.
    See docs/PERMISSIONS.md for the full permission model.
    """
    user.groups.add(Group.objects.get(name="Staff"))
