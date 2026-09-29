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
