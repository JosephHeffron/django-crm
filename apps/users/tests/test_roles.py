from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.test import RequestFactory, TestCase
from django.views import View

from apps.users.models import UserProfile, get_profile
from apps.users.roles import (
    OWNER_ONLY,
    Role,
    RoleRequiredMixin,
    clear_role_cache,
    has_role,
    user_role,
)

User = get_user_model()


class UserRoleTests(TestCase):
    def test_anonymous_and_none_have_no_role(self):
        self.assertIsNone(user_role(AnonymousUser()))
        self.assertIsNone(user_role(None))

    def test_user_without_a_role_group_has_no_role(self):
        self.assertIsNone(user_role(User.objects.create_user("new")))

    def test_group_membership_sets_the_role(self):
        user = User.objects.create_user("crew")
        user.groups.add(Group.objects.get(name="Cleaner"))
        self.assertEqual(user_role(user), Role.CLEANER)

    def test_superuser_is_always_owner(self):
        admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.assertEqual(user_role(admin), Role.OWNER)

    def test_most_privileged_role_wins_when_in_several(self):
        user = User.objects.create_user("both")
        user.groups.add(Group.objects.get(name="Cleaner"), Group.objects.get(name="Sales Rep"))
        self.assertEqual(user_role(user), Role.SALES_REP)

    def test_role_is_cached_per_instance_until_cleared(self):
        user = User.objects.create_user("promoted")
        self.assertIsNone(user_role(user))
        user.groups.add(Group.objects.get(name="Owner"))
        self.assertIsNone(user_role(user))  # stale, by design
        clear_role_cache(user)
        self.assertEqual(user_role(user), Role.OWNER)

    def test_has_role(self):
        admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.assertTrue(has_role(admin, OWNER_ONLY))
        self.assertFalse(has_role(User.objects.create_user("x"), OWNER_ONLY))


class _OwnerOnlyView(RoleRequiredMixin, View):
    allowed_roles = OWNER_ONLY

    def get(self, request):
        from django.http import HttpResponse

        return HttpResponse("ok")


class RoleRequiredMixinTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = _OwnerOnlyView.as_view()

    def _get(self, user):
        request = self.factory.get("/owner-only/")
        request.user = user
        return self.view(request)

    def test_anonymous_is_redirected_to_login(self):
        response = self._get(AnonymousUser())
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_wrong_role_is_forbidden(self):
        from django.core.exceptions import PermissionDenied

        user = User.objects.create_user("rep")
        user.groups.add(Group.objects.get(name="Sales Rep"))
        with self.assertRaises(PermissionDenied):
            self._get(user)

    def test_allowed_role_passes(self):
        admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.assertEqual(self._get(admin).status_code, 200)


class UserProfileTests(TestCase):
    def test_get_profile_creates_once(self):
        user = User.objects.create_user("jane")
        first = get_profile(user)
        second = get_profile(user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(UserProfile.objects.filter(user=user).count(), 1)
        self.assertEqual(first.calendar_tone, 1)
