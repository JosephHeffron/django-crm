"""Bringing a customer list in from a spreadsheet (Phase 22).

The rules these tests hold, because each one is a way an import can
quietly do damage:

- it **creates and never updates**, so a row matching somebody already
  on the books is left out and named rather than merged into them;
- a bad row is **skipped with its line number**, not fatal, and not
  silently dropped;
- it is **one transaction**, so a failure half way leaves nothing;
- it **invents nothing** — an unknown company or tag is reported and
  the customer imported without it, rather than a typo becoming a real
  tag forever.
"""

from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.crm import importers
from apps.crm.models import AuditLogEntry, Company, Contact, Property, Tag
from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

User = get_user_model()

PASSWORD = "correct-horse-battery"
IMPORT = reverse("crm:contact_import")

HEADER = "first_name,last_name,email,phone\n"


def upload(text, name="customers.csv"):
    """A CSV as the browser would hand it over."""
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


def read(text):
    return importers.read(upload(text))


class ReadingTests(TestCase):
    def test_a_header_and_rows_come_back_as_dicts(self):
        rows, unknown = read(HEADER + "Pat,Homeowner,pat@example.test,585-555-0100\n")
        self.assertEqual(unknown, [])
        self.assertEqual(
            rows,
            [
                (
                    2,
                    {
                        "first_name": "Pat",
                        "last_name": "Homeowner",
                        "email": "pat@example.test",
                        "phone": "585-555-0100",
                    },
                )
            ],
        )

    def test_the_line_number_is_the_line_in_the_file(self):
        """Reported back to the person, who has the file open in front
        of them — so it counts the header, like their spreadsheet
        does."""
        rows, _ = read(HEADER + "A,One\nB,Two\n")
        self.assertEqual([line for line, _ in rows], [2, 3])

    def test_column_names_are_matched_however_they_are_written(self):
        rows, unknown = read("First Name,LAST-NAME\nPat,Homeowner\n")
        self.assertEqual(unknown, [])
        self.assertEqual(rows[0][1]["first_name"], "Pat")
        self.assertEqual(rows[0][1]["last_name"], "Homeowner")

    def test_a_byte_order_mark_does_not_become_part_of_the_first_column(self):
        """Excel writes one. Without handling it the first column is
        called "﻿first_name" and the file looks like it has no
        name column at all."""
        raw = ("﻿" + HEADER + "Pat,Homeowner,,\n").encode("utf-8")
        rows, _ = importers.read(SimpleUploadedFile("c.csv", raw, content_type="text/csv"))
        self.assertEqual(rows[0][1]["first_name"], "Pat")

    def test_a_file_saved_by_excel_on_windows_is_read(self):
        raw = (HEADER + "Renée,Homeowner,,\n").encode("cp1252")
        rows, _ = importers.read(SimpleUploadedFile("c.csv", raw, content_type="text/csv"))
        self.assertEqual(rows[0][1]["first_name"], "Renée")

    def test_blank_lines_are_skipped(self):
        rows, _ = read(HEADER + "Pat,Homeowner,,\n\n,,,\n")
        self.assertEqual(len(rows), 1)

    def test_columns_it_does_not_understand_are_reported(self):
        """Reported, not ignored in silence: a column of data nobody
        notices being dropped is the worst outcome of an import."""
        rows, unknown = read("first_name,last_name,favourite_dog\nPat,Homeowner,Rex\n")
        self.assertEqual(unknown, ["favourite_dog"])
        self.assertNotIn("favourite_dog", rows[0][1])

    def test_the_columns_the_export_writes_and_import_cannot_use_are_not_unknown(self):
        """`owner`, `active` and `created` come straight off the export.
        Calling them unknown would warn about every file exported from
        here."""
        _, unknown = read("first_name,last_name,owner,active,created,address\nPat,H,Sam,True,x,y\n")
        self.assertEqual(unknown, [])

    def test_an_empty_file_says_so(self):
        for text, expected in (("", "empty"), (HEADER, "nothing else")):
            with self.assertRaises(importers.Problem) as refused:
                read(text)
            self.assertIn(expected, str(refused.exception))

    def test_a_file_with_no_name_column_says_which_is_missing(self):
        with self.assertRaises(importers.Problem) as refused:
            read("email,phone\npat@example.test,585\n")
        self.assertIn("first_name", str(refused.exception))
        self.assertIn("last_name", str(refused.exception))

    def test_too_many_rows_is_refused_rather_than_truncated(self):
        """Importing the first 2,000 and saying nothing is the one thing
        worse than refusing."""
        body = HEADER + "".join(f"P{n},Homeowner,,\n" for n in range(importers.MAX_ROWS + 1))
        with self.assertRaises(importers.Problem) as refused:
            read(body)
        self.assertIn(str(importers.MAX_ROWS), str(refused.exception))

    def test_too_big_a_file_is_refused_before_it_is_parsed(self):
        big = BytesIO(b"x" * (importers.MAX_BYTES + 1))
        fat = SimpleUploadedFile("c.csv", big.getvalue(), content_type="text/csv")
        with self.assertRaises(importers.Problem) as refused:
            importers.read(fat)
        self.assertIn("limit", str(refused.exception))

    def test_the_exports_formula_guard_is_undone(self):
        """`apps/core/export.py` writes a leading apostrophe before a
        cell starting with "=" so a spreadsheet can't run it. A round
        trip must not leave that apostrophe in somebody's name."""
        rows, _ = read(HEADER + "'=Pat,'=Homeowner,,\n")
        self.assertEqual(rows[0][1]["first_name"], "=Pat")
        self.assertEqual(rows[0][1]["last_name"], "=Homeowner")

    def test_an_apostrophe_that_belongs_to_the_name_is_left_alone(self):
        """The leading one is the case that matters, and the first
        version of this test used "O'Pat" — where the apostrophe is in
        the middle, so it never exercised the rule at all. "'t Hooft"
        is a real surname that starts with one."""
        rows, _ = read(HEADER + "'t Hooft,O'Homeowner,,\n")
        self.assertEqual(rows[0][1]["first_name"], "'t Hooft")
        self.assertEqual(rows[0][1]["last_name"], "O'Homeowner")


class PlanningTests(TestCase):
    def setUp(self):
        self.user = grant_role(f.user("boss"), Role.OWNER)

    def plan(self, text, **extra):
        rows, _ = read(text)
        return importers.plan(rows, **extra)

    def test_a_good_row_is_ready_to_import(self):
        planned = self.plan(HEADER + "Pat,Homeowner,pat@example.test,585-555-0100\n")
        self.assertTrue(planned[0].importing)
        self.assertEqual(planned[0].problems, [])

    def test_a_bad_email_leaves_the_row_out_and_says_which_line(self):
        planned = self.plan(HEADER + "Pat,Homeowner,not-an-email,\n")
        self.assertFalse(planned[0].importing)
        self.assertEqual(planned[0].line, 2)
        self.assertIn("email", planned[0].problems[0])

    def test_a_row_with_no_surname_is_left_out(self):
        planned = self.plan(HEADER + "Pat,,,\n")
        self.assertFalse(planned[0].importing)
        self.assertIn("last_name", planned[0].problems[0])

    def test_one_bad_row_does_not_stop_the_others(self):
        planned = self.plan(HEADER + "Pat,Homeowner,bad-email,\nSam,Renter,sam@example.test,\n")
        self.assertFalse(planned[0].importing)
        self.assertTrue(planned[1].importing)

    def test_half_an_address_is_refused_rather_than_dropped(self):
        """`Property` needs all four and nothing here has a default for
        any of them, so importing the customer and losing their street
        would be the silent wrong answer."""
        planned = self.plan("first_name,last_name,street,city\nPat,Homeowner,1 Elm St,Webster\n")
        self.assertFalse(planned[0].importing)
        self.assertIn("state", planned[0].problems[0])
        self.assertIn("postal_code", planned[0].problems[0])

    def test_a_whole_address_is_fine(self):
        planned = self.plan(
            "first_name,last_name,street,city,state,postal_code\n"
            "Pat,Homeowner,1 Elm St,Webster,NY,14580\n"
        )
        self.assertTrue(planned[0].importing, planned[0].problems)

    def test_a_stage_written_the_way_a_person_writes_it_is_accepted(self):
        """The export writes "customer"; somebody editing the file in a
        spreadsheet writes "Customer", and refusing that is pedantry."""
        planned = self.plan("first_name,last_name,stage\nPat,Homeowner,Customer\n")
        self.assertTrue(planned[0].importing, planned[0].problems)
        self.assertEqual(planned[0].values["stage"], Contact.Status.CUSTOMER)

    def test_a_label_that_is_not_just_the_value_capitalised_is_accepted(self):
        """ "Customer" only differs from "customer" by case, so matching
        on the label looks tested when only the value is being matched.
        "Yard sign" is stored as "yard_sign", which tells the two
        apart — a mutation pass found this."""
        planned = self.plan("first_name,last_name,lead_source\nPat,Homeowner,Yard sign\n")
        self.assertTrue(planned[0].importing, planned[0].problems)
        self.assertEqual(planned[0].values["lead_source"], Contact.LeadSource.YARD_SIGN)

    def test_a_stage_that_is_not_a_stage_is_refused(self):
        planned = self.plan("first_name,last_name,stage\nPat,Homeowner,Prospect\n")
        self.assertFalse(planned[0].importing)
        self.assertIn("stage", planned[0].problems[0])

    def test_an_unknown_company_is_reported_and_the_customer_still_imported(self):
        """Creating it would mean a typo in one row becoming a company
        on the books."""
        planned = self.plan("first_name,last_name,company\nPat,Homeowner,Nobody Ltd\n")
        self.assertTrue(planned[0].importing)
        self.assertIsNone(planned[0].values["company"])
        self.assertIn("Nobody Ltd", planned[0].notes[0])

    def test_a_company_already_on_the_books_is_linked_however_it_is_cased(self):
        company = Company.objects.create(name="Elm Properties", created_by=self.user)
        planned = self.plan("first_name,last_name,company\nPat,Homeowner,elm properties\n")
        self.assertEqual(planned[0].values["company"], company)
        self.assertEqual(planned[0].notes, [])

    def test_an_unknown_tag_is_reported_and_the_known_ones_still_applied(self):
        gutters = Tag.objects.create(name="Gutters")
        planned = self.plan('first_name,last_name,tags\nPat,Homeowner,"Gutters, Nonsense"\n')
        self.assertEqual(planned[0].values["tag_objects"], [gutters])
        self.assertIn("Nonsense", planned[0].notes[0])

    def test_somebody_already_on_the_books_is_left_out_and_named(self):
        Contact.objects.create(
            first_name="Pat", last_name="Homeowner", email="pat@example.test", created_by=self.user
        )
        planned = self.plan(HEADER + "Pat,Homeowner,pat@example.test,\n")
        self.assertFalse(planned[0].importing)
        self.assertIn("already on the books", planned[0].problems[0])
        self.assertIn("Pat Homeowner", planned[0].problems[0])
        self.assertIn("the same name", planned[0].problems[0])

    def test_the_tick_box_imports_them_anyway(self):
        Contact.objects.create(first_name="Pat", last_name="Homeowner", created_by=self.user)
        planned = self.plan(HEADER + "Pat,Homeowner,,\n", include_duplicates=True)
        self.assertTrue(planned[0].importing)
        self.assertIn("Pat Homeowner", planned[0].duplicate)

    def test_the_same_person_twice_in_one_file_is_caught(self):
        """Nothing is written while planning, so the database check
        cannot see this: without its own check the second row would
        import as a second customer."""
        planned = self.plan(HEADER + "Pat,Homeowner,,585-555-0100\nPat,Homeowner,,585-555-0100\n")
        self.assertTrue(planned[0].importing)
        self.assertFalse(planned[1].importing)
        self.assertIn("line 2 of this file", planned[1].problems[0])

    def test_two_different_people_in_one_file_both_import(self):
        planned = self.plan(HEADER + "Pat,Homeowner,,585-555-0100\nSam,Renter,,585-555-0199\n")
        self.assertTrue(all(entry.importing for entry in planned))


class ApplyingTests(TestCase):
    def setUp(self):
        self.user = grant_role(f.user("boss"), Role.OWNER)

    def run_import(self, text, **extra):
        rows, _ = read(text)
        planned = importers.plan(rows, **extra)
        return importers.apply(planned, self.user), planned

    def test_it_creates_the_customer_with_their_details(self):
        (customers, addresses), _ = self.run_import(
            "first_name,last_name,email,phone,stage,title,notes\n"
            "Pat,Homeowner,pat@example.test,585-555-0100,lead,Owner,Back gate\n"
        )
        self.assertEqual((customers, addresses), (1, 0))
        pat = Contact.objects.get(last_name="Homeowner")
        self.assertEqual(pat.email, "pat@example.test")
        self.assertEqual(pat.phone, "585-555-0100")
        self.assertEqual(pat.status, Contact.Status.LEAD)
        self.assertEqual(pat.title, "Owner")
        self.assertEqual(pat.notes, "Back gate")

    def test_a_row_with_no_stage_is_a_customer(self):
        self.run_import(HEADER + "Pat,Homeowner,,\n")
        self.assertEqual(Contact.objects.get().status, Contact.Status.CUSTOMER)

    def test_the_person_importing_owns_what_they_brought_in(self):
        self.run_import(HEADER + "Pat,Homeowner,,\n")
        pat = Contact.objects.get()
        self.assertEqual(pat.owner, self.user)
        self.assertEqual(pat.created_by, self.user)

    def test_an_address_becomes_their_main_one_and_is_not_placed(self):
        """Nothing is geocoded here — placing an address is an explicit
        action — so these arrive unplaced for the map page to list."""
        (_, addresses), _ = self.run_import(
            "first_name,last_name,street,city,state,postal_code\n"
            "Pat,Homeowner,1 Elm St,Webster,NY,14580\n"
        )
        self.assertEqual(addresses, 1)
        address = Property.objects.get()
        self.assertEqual(address.street, "1 Elm St")
        self.assertTrue(address.is_primary)
        self.assertIsNone(address.located_at)
        self.assertIsNone(address.latitude)

    def test_tags_are_applied(self):
        Tag.objects.create(name="Gutters")
        self.run_import("first_name,last_name,tags\nPat,Homeowner,Gutters\n")
        self.assertEqual([tag.name for tag in Contact.objects.get().tags.all()], ["Gutters"])

    def test_every_customer_imported_is_in_the_change_log(self):
        self.run_import(
            "first_name,last_name,street,city,state,postal_code\n"
            "Pat,Homeowner,1 Elm St,Webster,NY,14580\n"
        )
        for model in (Contact, Property):
            entries = AuditLogEntry.objects.filter(
                content_type=ContentType.objects.get_for_model(model),
                action=AuditLogEntry.Action.CREATED,
            )
            self.assertEqual(entries.count(), 1, model.__name__)
            self.assertEqual(entries.get().user, self.user)

    def test_rows_that_were_left_out_are_not_created(self):
        (customers, _), planned = self.run_import(
            HEADER + "Pat,Homeowner,bad-email,\nSam,Renter,,\n"
        )
        self.assertEqual(customers, 1)
        self.assertEqual([c.last_name for c in Contact.objects.all()], ["Renter"])
        self.assertFalse(planned[0].importing)

    def test_a_failure_half_way_leaves_nothing_behind(self):
        """The transaction, asserted rather than claimed: an import that
        half happened, with no way to see where it stopped, is the worst
        outcome there is."""
        rows, _ = read(HEADER + "Pat,Homeowner,,\nSam,Renter,,\nLee,Landlord,,\n")
        planned = importers.plan(rows)
        real = Contact.objects.create

        def fail_on_the_third(*args, **kwargs):
            if kwargs.get("last_name") == "Landlord":
                raise RuntimeError("database went away")
            return real(*args, **kwargs)

        with mock.patch.object(Contact.objects, "create", side_effect=fail_on_the_third):
            with self.assertRaises(RuntimeError):
                importers.apply(planned, self.user)
        self.assertEqual(Contact.objects.count(), 0)
        self.assertEqual(AuditLogEntry.objects.count(), 0)


class PageTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)

    def test_the_page_explains_what_the_file_needs(self):
        response = self.client.get(IMPORT)
        self.assertEqual(response.status_code, 200)
        for column in ("first_name", "postal_code"):
            self.assertContains(response, column)

    def test_business_settings_links_to_it(self):
        """Its only entrance, beside the export it is the other half
        of."""
        response = self.client.get(reverse("core:business_settings"))
        self.assertContains(response, IMPORT)

    def test_checking_a_file_saves_nothing(self):
        response = self.client.post(
            IMPORT,
            {"csv_file": upload(HEADER + "Pat,Homeowner,,\n"), "check_only": "on"},
        )
        self.assertContains(response, "would be")
        self.assertEqual(Contact.objects.count(), 0)

    def test_importing_for_real_creates_them_and_reports(self):
        response = self.client.post(
            IMPORT,
            {"csv_file": upload(HEADER + "Pat,Homeowner,,\nSam,Renter,bad-email,\n")},
            follow=True,
        )
        self.assertEqual(Contact.objects.count(), 1)
        self.assertContains(response, "Imported 1 customer and 0 addresses.")
        self.assertContains(response, "Left out")

    def test_a_file_it_cannot_read_is_refused_without_saving_anything(self):
        response = self.client.post(IMPORT, {"csv_file": upload("nothing,useful\n1,2\n")})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "first_name")
        self.assertEqual(Contact.objects.count(), 0)

    def test_a_sales_rep_cannot_reach_it(self):
        """Owner-only, like the export it sits beside: this is the one
        page that writes hundreds of records from one click."""
        grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)
        self.assertEqual(self.client.get(IMPORT).status_code, 403)
        self.assertEqual(
            self.client.post(
                IMPORT, {"csv_file": upload(HEADER + "Pat,Homeowner,,\n")}
            ).status_code,
            403,
        )
        self.assertEqual(Contact.objects.count(), 0)
