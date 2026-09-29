"""Exercise the Phase 17 data migrations' functions directly against the
real app registry (they only use apps.get_model), on data created here
— the migration already ran once, empty, when the test DB was built."""

import importlib
from datetime import date
from decimal import Decimal

from django.apps import apps as global_apps
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from apps.crm.models import Company, Contact, Deal, Lead, Task
from apps.jobs.models import Quote

from . import _factories as f

fold_migration = importlib.import_module("apps.jobs.migrations.0003_fold_leads_and_deals")


class FoldLeadsAndDealsTests(TestCase):
    def setUp(self):
        self.owner = f.user()
        self.acme = Company.objects.create(name="Acme Property Mgmt", created_by=self.owner)

    def _fold(self):
        fold_migration.fold(global_apps, None)

    def test_open_lead_becomes_a_lead_contact(self):
        lead = Lead.objects.create(
            name="Jane Q Public",
            email="jane@example.com",
            phone="555-0100",
            source=Lead.Source.REFERRAL,
            notes="Wants windows",
            created_by=self.owner,
        )
        self._fold()
        contact = Contact.objects.get(legacy_lead_id=lead.pk)
        self.assertEqual((contact.first_name, contact.last_name), ("Jane", "Q Public"))
        self.assertEqual(contact.status, Contact.Status.LEAD)
        self.assertEqual(contact.lead_source, "referral")
        self.assertTrue(contact.is_active)
        self.assertEqual(contact.created_at, lead.created_at)

    def test_unqualified_lead_becomes_inactive(self):
        lead = Lead.objects.create(
            name="Nope", status=Lead.Status.UNQUALIFIED, created_by=self.owner
        )
        self._fold()
        self.assertFalse(Contact.objects.get(legacy_lead_id=lead.pk).is_active)

    def test_lead_company_links_to_existing_company_else_goes_to_notes(self):
        linked = Lead.objects.create(
            name="Linked Person", company_name="acme property mgmt", created_by=self.owner
        )
        unknown = Lead.objects.create(
            name="Other Person", company_name="Nobody Inc", created_by=self.owner
        )
        self._fold()
        self.assertEqual(Contact.objects.get(legacy_lead_id=linked.pk).company, self.acme)
        orphan = Contact.objects.get(legacy_lead_id=unknown.pk)
        self.assertIsNone(orphan.company)
        self.assertIn("Company: Nobody Inc", orphan.notes)

    def test_converted_lead_only_backfills_its_contacts_lead_source(self):
        existing = f.contact(self.owner, "Already", "Converted")
        Lead.objects.create(
            name="Already Converted",
            source=Lead.Source.EVENT,
            status=Lead.Status.CONVERTED,
            converted_contact=existing,
            created_by=self.owner,
        )
        before = Contact.objects.count()
        self._fold()
        self.assertEqual(Contact.objects.count(), before)
        existing.refresh_from_db()
        self.assertEqual(existing.lead_source, "event")

    def test_deal_becomes_quote_with_one_line_and_moved_tasks(self):
        person = f.contact(self.owner, "Deal", "Person")
        deal = Deal.objects.create(
            title="Whole-house windows",
            contact=person,
            value=Decimal("480.00"),
            stage=Deal.Stage.PROPOSAL,
            expected_close_date=date(2026, 11, 1),
            created_by=self.owner,
        )
        task = Task.objects.create(
            title="Call back", deal=deal, assigned_to=self.owner, created_by=self.owner
        )
        self._fold()
        quote = Quote.objects.get(legacy_deal_id=deal.pk)
        self.assertEqual(quote.contact, person)
        self.assertEqual(quote.status, Quote.Status.SENT)
        self.assertEqual(quote.total, Decimal("480.00"))
        self.assertEqual(quote.line_items.get().description, "Whole-house windows")
        self.assertIn("Expected close: 2026-11-01", quote.notes)
        task.refresh_from_db()
        self.assertEqual(task.quote, quote)

    def test_won_deal_is_accepted_and_makes_the_contact_a_customer(self):
        person = f.contact(self.owner, "Won", "Deal", status=Contact.Status.LEAD)
        closed = timezone.now()
        deal = Deal.objects.create(
            title="Gutters",
            contact=person,
            value=Decimal("175"),
            stage=Deal.Stage.CLOSED_WON,
            closed_at=closed,
            created_by=self.owner,
        )
        self._fold()
        quote = Quote.objects.get(legacy_deal_id=deal.pk)
        self.assertEqual((quote.status, quote.accepted_at), (Quote.Status.ACCEPTED, closed))
        person.refresh_from_db()
        self.assertEqual(person.status, Contact.Status.CUSTOMER)

    def test_company_only_deal_uses_first_company_contact_else_a_placeholder(self):
        first = f.contact(self.owner, "First", "AtAcme", company=self.acme)
        f.contact(self.owner, "Second", "AtAcme", company=self.acme)
        acme_deal = Deal.objects.create(title="Acme job", company=self.acme, created_by=self.owner)
        lonely = Company.objects.create(name="No Contacts LLC", created_by=self.owner)
        lonely_deal = Deal.objects.create(title="Lonely job", company=lonely, created_by=self.owner)

        self._fold()

        self.assertEqual(Quote.objects.get(legacy_deal_id=acme_deal.pk).contact, first)
        placeholder = Quote.objects.get(legacy_deal_id=lonely_deal.pk).contact
        self.assertEqual((placeholder.first_name, placeholder.company), ("No Contacts LLC", lonely))
        self.assertEqual(placeholder.notes, fold_migration.PLACEHOLDER_NOTE)

    def test_reverse_removes_exactly_what_the_fold_added(self):
        untouched = f.contact(self.owner, "Pre", "Existing")
        Lead.objects.create(name="Lead Person", created_by=self.owner)
        lonely = Company.objects.create(name="Solo Co", created_by=self.owner)
        deal = Deal.objects.create(title="Solo job", company=lonely, created_by=self.owner)
        task = Task.objects.create(
            title="t", deal=deal, assigned_to=self.owner, created_by=self.owner
        )
        self._fold()

        with connection.schema_editor() as schema_editor:
            fold_migration.unfold(global_apps, schema_editor)

        self.assertEqual(list(Contact.objects.all()), [untouched])
        self.assertFalse(Quote.objects.exists())
        task.refresh_from_db()
        self.assertIsNone(task.quote)
        self.assertEqual(task.deal, deal)
        self.assertTrue(Lead.objects.exists() and Deal.objects.exists())

    def test_reverse_refuses_when_later_work_depends_on_folded_data(self):
        # unfold deletes by primary key (not through Django's collector,
        # which breaks in multi-app backwards migrations), so it's
        # PostgreSQL's FK constraint that stops it from orphaning a job.
        lead = Lead.objects.create(name="Became Customer", created_by=self.owner)
        self._fold()
        f.job(Contact.objects.get(legacy_lead_id=lead.pk), self.owner)

        with self.assertRaises(IntegrityError), transaction.atomic():
            # Django's PostgreSQL FKs are DEFERRABLE INITIALLY DEFERRED: in
            # a real migration the violation fires at commit. The test's
            # wrapping transaction never commits, so check immediately.
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            with connection.schema_editor() as schema_editor:
                fold_migration.unfold(global_apps, schema_editor)
        self.assertTrue(Contact.objects.filter(legacy_lead_id=lead.pk).exists())
