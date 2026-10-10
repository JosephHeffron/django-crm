"""A Save button at the top of every form (Phase 18.5 unit 6).

A long form meant scrolling to the bottom to save it. The header button
reaches its form through the HTML `form` attribute, which is this
project's first use of that. It is plain HTML, so nothing in the
production Content-Security-Policy had to change.

Two kinds of test. The structural ones read the template directory, so
a form added later cannot quietly skip the pattern or point its button
at a form that is not there. The rendered ones fetch each real page,
because a `form=` naming nothing silently does nothing at all — no
error, no warning, the button simply never submits.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.crm.models import Company, Contact, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Quote, ServiceType
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"
ROOT = Path(settings.BASE_DIR)

# Every record form, and the id its header button must name.
FORM_TEMPLATES = {
    "apps/crm/templates/crm/contact_form.html": "contact-form",
    "apps/crm/templates/crm/company_form.html": "company-form",
    "apps/crm/templates/crm/lead_form.html": "lead-form",
    "apps/crm/templates/crm/deal_form.html": "deal-form",
    "apps/crm/templates/crm/task_form.html": "task-form",
    "apps/crm/templates/crm/activity_form.html": "activity-form",
    "apps/crm/templates/crm/property_form.html": "address-form",
    "apps/jobs/templates/jobs/job_form.html": "job-form",
    "apps/jobs/templates/jobs/quote_form.html": "quote-form",
    "apps/jobs/templates/jobs/invoice_form.html": "invoice-form",
    "apps/jobs/templates/jobs/payment_form.html": "payment-form",
    "apps/jobs/templates/jobs/expense_form.html": "expense-form",
    "apps/jobs/templates/jobs/service_form.html": "service-form",
    "apps/users/templates/users/profile_form.html": "profile-form",
}

# Deliberately left out: each hosts several independent forms, so one
# header Save would be ambiguous about which it saves. Listed rather
# than omitted, so the sweep below reports a genuinely new template
# instead of silently tolerating these.
MULTI_FORM_PAGES = {
    "apps/core/templates/core/business_settings.html",
    "apps/core/templates/core/goals.html",
    "apps/users/templates/users/profile.html",
}


class TemplateShapeTests(SimpleTestCase):
    def test_there_are_templates_to_check(self):
        # A path typo would otherwise make every test below vacuous.
        for path in FORM_TEMPLATES:
            self.assertTrue((ROOT / path).exists(), path)

    def test_every_form_has_an_id_and_a_header_save(self):
        missing = []
        for path, form_id in FORM_TEMPLATES.items():
            text = (ROOT / path).read_text()
            if f'id="{form_id}"' not in text:
                missing.append(f"{path}: no form with id={form_id}")
            if "partials/_save_button.html" not in text:
                missing.append(f"{path}: no header save button")
            elif f'form_id="{form_id}"' not in text:
                missing.append(f"{path}: the button does not name {form_id}")
        self.assertEqual(missing, [])

    def test_every_button_names_a_form_on_its_own_page(self):
        """A `form=` pointing at nothing fails silently.

        So the id and the reference are checked against each other
        rather than each being checked alone.
        """
        wrong = []
        for path in FORM_TEMPLATES:
            text = (ROOT / path).read_text()
            for named in re.findall(r'form_id="([^"]+)"', text):
                if f'id="{named}"' not in text:
                    wrong.append(f"{path}: button names {named}, no such form")
        self.assertEqual(wrong, [])

    def test_each_page_has_one_form_and_one_id(self):
        clashes = []
        for path in FORM_TEMPLATES:
            text = (ROOT / path).read_text()
            ids = re.findall(r"<form[^>]*\sid=\"([^\"]+)\"", text)
            if len(ids) != len(set(ids)):
                clashes.append(f"{path}: duplicate ids {ids}")
        self.assertEqual(clashes, [])

    def test_no_record_form_template_was_missed(self):
        """Walks the directories rather than trusting the list above.

        This is the only test here that notices a form template added
        later without a header save.
        """
        found = {str(p.relative_to(ROOT)) for p in ROOT.glob("apps/*/templates/**/*_form.html")}
        self.assertTrue(found, "the glob matched nothing")
        unlisted = found - set(FORM_TEMPLATES) - MULTI_FORM_PAGES
        self.assertEqual(
            sorted(unlisted),
            [],
            "these look like record forms with no header save: wire them up, or "
            "list them in MULTI_FORM_PAGES with a reason",
        )

    def test_no_submit_button_carries_a_name(self):
        """What makes the header button safe as the default.

        The default submit — the one the Enter key presses — is the
        first in document order whose owner is that form, which is now
        the header button. That changes nothing observable only because
        no submit button on these pages carries `name` or `value`, so
        which one was pressed cannot be told apart. If one ever does,
        this fails and the ordering needs thinking about again.
        """
        named = []
        for path in FORM_TEMPLATES:
            for tag in re.findall(r"<button[^>]*>", (ROOT / path).read_text()):
                if 'type="submit"' in tag and " name=" in tag:
                    named.append(f"{path}: {tag}")
        self.assertEqual(named, [])

    def test_the_partial_uses_no_javascript_and_nothing_inline(self):
        text = (ROOT / "templates/partials/_save_button.html").read_text()
        self.assertIn('form="{{ form_id }}"', text)
        self.assertNotIn("<script", text)
        self.assertNotIn("onclick", text)
        self.assertNotIn("style=", text)


class RenderedPageTests(TestCase):
    """And the pages as a browser actually receives them."""

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.customer = f.contact(self.owner)
        self.service = f.service()
        self.client.login(username="boss", password=PASSWORD)

    def pages(self):
        company = Company.objects.create(name="Acme", created_by=self.owner)
        job = f.job(self.customer, self.owner, lines=[])
        quote = Quote.objects.create(contact=self.customer, prepared_by=self.owner)
        invoice = f.invoice(job)
        task = Task.objects.create(title="A task", assigned_to=self.owner, created_by=self.owner)
        return [
            (reverse("crm:contact_create"), "contact-form"),
            (reverse("crm:contact_update", args=[self.customer.pk]), "contact-form"),
            (reverse("crm:company_create"), "company-form"),
            (reverse("crm:company_update", args=[company.pk]), "company-form"),
            (reverse("crm:task_create"), "task-form"),
            (reverse("crm:task_update", args=[task.pk]), "task-form"),
            (reverse("crm:activity_create"), "activity-form"),
            (reverse("crm:property_create"), "address-form"),
            (reverse("jobs:job_create"), "job-form"),
            (reverse("jobs:job_update", args=[job.pk]), "job-form"),
            (reverse("jobs:quote_create"), "quote-form"),
            (reverse("jobs:quote_update", args=[quote.pk]), "quote-form"),
            (reverse("jobs:invoice_update", args=[invoice.pk]), "invoice-form"),
            (reverse("jobs:payment_create", args=[invoice.pk]), "payment-form"),
            (reverse("jobs:expense_create"), "expense-form"),
            (
                reverse("jobs:service_update", args=[ServiceType.objects.first().pk]),
                "service-form",
            ),
            (reverse("people:profile_edit"), "profile-form"),
        ]

    def test_there_are_pages_to_check(self):
        self.assertGreater(len(self.pages()), 15)

    def test_every_form_page_offers_a_save_in_its_header(self):
        bad = []
        for url, form_id in self.pages():
            response = self.client.get(url)
            if response.status_code != 200:
                bad.append(f"{url}: {response.status_code}")
                continue
            body = response.content.decode()
            if f'id="{form_id}"' not in body:
                bad.append(f"{url}: no form id={form_id}")
            if f'form="{form_id}"' not in body:
                bad.append(f"{url}: no header button for {form_id}")
        self.assertEqual(bad, [])

    def test_the_header_button_comes_before_the_form(self):
        """It is only useful if it is reached without scrolling."""
        late = []
        for url, form_id in self.pages():
            body = self.client.get(url).content.decode()
            if f'form="{form_id}"' not in body:
                continue
            if body.index(f'form="{form_id}"') > body.index(f'id="{form_id}"'):
                late.append(url)
        self.assertEqual(late, [])

    def test_a_long_form_offers_two_saves_not_one(self):
        # The job form is the longest, which is what prompted this.
        body = self.client.get(reverse("jobs:job_create")).content.decode()
        self.assertLess(body.index('form="job-form"'), body.index('id="job-form"'))
        self.assertGreater(body.count('type="submit"'), 1)

    def test_saving_a_record_still_works(self):
        """The header button is outside the form element.

        An unassociated button sends nothing at all, so that the form
        saves is worth asserting rather than assuming.
        """
        self.client.post(
            reverse("crm:contact_create"),
            {
                "first_name": "Top",
                "last_name": "Saved",
                "status": Contact.Status.CUSTOMER,
                "is_active": "on",
            },
        )
        self.assertTrue(Contact.objects.filter(last_name="Saved").exists())

    def test_the_settings_pages_are_left_alone(self):
        """Several independent forms, so one header Save is ambiguous."""
        for url in (reverse("core:goals"), reverse("people:profile")):
            body = self.client.get(url).content.decode()
            self.assertNotIn("partials/_save_button.html", body)
            self.assertNotIn('form="', body)
