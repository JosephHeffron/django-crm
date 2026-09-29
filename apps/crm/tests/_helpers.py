"""Shared test helpers — not itself a test module (leading underscore
keeps Django's test*.py discovery from picking it up).
"""

from django.contrib.auth.models import Group

from apps.users.roles import Role, clear_role_cache


def grant_role(user, role=Role.SALES_REP):
    """Put user in a role group (seeded by users/0002_roles). Sales Rep
    is the default: it holds the add/change permissions the old "Staff"
    group did, which is what most view tests exercise. See
    docs/decisions/0008-roles-and-row-level-scoping.md."""
    user.groups.add(Group.objects.get(name=role.value))
    clear_role_cache(user)
    return user
