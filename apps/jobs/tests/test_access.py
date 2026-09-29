from django.test import TestCase

from apps.crm.models import Contact
from apps.crm.tests._helpers import grant_role
from apps.jobs.access import contacts_for, invoices_for, jobs_for, quotes_for
from apps.users.roles import Role

from . import _factories as f


class RowLevelScopingTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("owner"), Role.OWNER)
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.crew_a = grant_role(f.user("crew_a"), Role.CLEANER)
        self.crew_b = grant_role(f.user("crew_b"), Role.CLEANER)
        self.nobody = f.user("nobody")

        self.alice = f.contact(self.owner, "Alice", "A")
        self.bob = f.contact(self.owner, "Bob", "B")
        self.carol = f.contact(self.owner, "Carol", "C")  # no jobs at all
        self.job_a = f.job(self.alice, self.owner)
        self.job_b = f.job(self.bob, self.owner)
        f.assign(self.job_a, self.crew_a)
        f.assign(self.job_b, self.crew_b)
        self.quote = f.quote(self.carol, self.rep)
        self.invoice = f.invoice(self.job_a)

    def test_sales_roles_see_every_job_contact_and_quote(self):
        for user in (self.owner, self.rep):
            self.assertEqual(set(jobs_for(user)), {self.job_a, self.job_b})
            self.assertEqual(set(contacts_for(user)), set(Contact.objects.all()))
            self.assertEqual(list(quotes_for(user)), [self.quote])

    def test_cleaner_sees_only_their_assigned_jobs_and_those_customers(self):
        self.assertEqual(list(jobs_for(self.crew_a)), [self.job_a])
        self.assertEqual(list(contacts_for(self.crew_a)), [self.alice])
        self.assertEqual(list(quotes_for(self.crew_a)), [])

    def test_no_role_sees_nothing(self):
        self.assertFalse(jobs_for(self.nobody).exists())
        self.assertFalse(contacts_for(self.nobody).exists())
        self.assertFalse(quotes_for(self.nobody).exists())

    def test_only_owner_sees_invoices(self):
        self.assertEqual(list(invoices_for(self.owner)), [self.invoice])
        self.assertFalse(invoices_for(self.rep).exists())
        self.assertFalse(invoices_for(self.crew_a).exists())

    def test_scoped_querysets_stay_safe_to_annotate(self):
        # pk__in subqueries (not JOINs) — totals aren't multiplied by the
        # assignment rows the scoping filter goes through.
        f.assign(self.job_a, self.owner)  # two crew rows on job_a
        crew_view = jobs_for(self.crew_a).with_totals().get()
        self.assertEqual(crew_view.total, self.job_a.total)
