from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.templatetags.crm_format import money, status_label


class MoneyFilterTests(SimpleTestCase):
    def test_formats_dollars(self):
        self.assertEqual(money(Decimal("1234.5")), "$1,234.50")
        self.assertEqual(money(0), "$0.00")
        self.assertEqual(money(Decimal("-20")), "-$20.00")
        self.assertEqual(money("99.999"), "$100.00")

    def test_missing_and_unparseable_values(self):
        self.assertEqual(money(None), "—")
        self.assertEqual(money(""), "—")
        self.assertEqual(money("n/a"), "n/a")


class StatusLabelTests(SimpleTestCase):
    def test_labels(self):
        self.assertEqual(status_label("partially_paid"), "Partially paid")
        self.assertEqual(status_label("in_progress"), "In progress")


class AvatarFilterTests(SimpleTestCase):
    def test_same_name_same_color_and_all_colors_reachable(self):
        from apps.core.templatetags.crm_format import avatar_class

        self.assertEqual(avatar_class("Alex Morgan"), avatar_class("Alex Morgan"))
        classes = {avatar_class(f"Person {i}") for i in range(60)}
        self.assertEqual(classes, {f"avatar-c{n}" for n in range(1, 6)})

    def test_initials(self):
        from types import SimpleNamespace

        from apps.core.templatetags.crm_format import initials

        self.assertEqual(initials("Alex Morgan"), "AM")
        self.assertEqual(initials("Cher"), "CH")
        user = SimpleNamespace(first_name="Jamie", last_name="Rivera")
        self.assertEqual(initials(user), "JR")
        nameless = SimpleNamespace(first_name="", last_name="", get_username=lambda: "crew7")
        self.assertEqual(initials(nameless), "CR")
