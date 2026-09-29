"""Owner / Sales Rep / Cleaner roles — the one place role logic lives.

See docs/decisions/0008-roles-and-row-level-scoping.md. Roles are Django
Groups (seeded by apps/users/migrations/0002_roles.py); a superuser always
counts as Owner; a user in no role group has no role and is denied every
CRM page (fail closed). Navigation (apps/core/navigation.py) is declared
against the same role sets, so a nav link and its page can't disagree.
"""

from enum import StrEnum

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class Role(StrEnum):
    # Declaration order is precedence when a user is (unusually) in
    # more than one role group: the most privileged role wins.
    OWNER = "Owner"
    SALES_REP = "Sales Rep"
    CLEANER = "Cleaner"


ALL_ROLES = frozenset(Role)
SALES_ROLES = frozenset({Role.OWNER, Role.SALES_REP})
OWNER_ONLY = frozenset({Role.OWNER})

# Cached per user *instance*. Django's auth middleware loads a fresh
# User object for every request, so this is effectively per-request —
# but code that changes a user's groups and then re-checks the role on
# the same instance must call clear_role_cache() first.
_ROLE_CACHE_ATTR = "_crm_role"


def user_role(user):
    """Return the user's Role, or None for anonymous/no-role users."""
    if user is None or not user.is_authenticated:
        return None
    if hasattr(user, _ROLE_CACHE_ATTR):
        return getattr(user, _ROLE_CACHE_ATTR)
    if user.is_superuser:
        role = Role.OWNER
    else:
        names = set(user.groups.values_list("name", flat=True))
        role = next((r for r in Role if r.value in names), None)
    setattr(user, _ROLE_CACHE_ATTR, role)
    return role


def roles_for(users):
    """{user.pk: Role or None} for many users in one query — the same
    rules as user_role(), for lists like the team page."""
    users = list(users)
    names = {}
    for user_id, name in (
        get_user_model()
        .groups.through.objects.filter(user_id__in=[u.pk for u in users])
        .values_list("user_id", "group__name")
    ):
        names.setdefault(user_id, set()).add(name)
    return {
        u.pk: Role.OWNER
        if u.is_superuser
        else next((r for r in Role if r.value in names.get(u.pk, ())), None)
        for u in users
    }


def clear_role_cache(user):
    if hasattr(user, _ROLE_CACHE_ATTR):
        delattr(user, _ROLE_CACHE_ATTR)


def has_role(user, roles):
    return user_role(user) in roles


class RoleRequiredMixin(LoginRequiredMixin):
    """Anonymous → login redirect; authenticated but wrong role → 403.

    Subclasses set ``allowed_roles``. Keep PermissionRequiredMixin on
    write views as well — this mixin decides who may use a page at all,
    model permissions still decide who may change data.
    """

    allowed_roles = frozenset()

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and user_role(request.user) not in self.allowed_roles:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class SalesRoleRequiredMixin(RoleRequiredMixin):
    """Customer-facing CRM pages: Owner and Sales Rep only."""

    allowed_roles = SALES_ROLES


class OwnerRequiredMixin(RoleRequiredMixin):
    allowed_roles = OWNER_ONLY
