import csv
import io
import json
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.core.models import BusinessLink, BusinessSettings
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Payment
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"
URL = reverse("core:business_settings")


def image_file(size=(800, 400), fmt="PNG", name="logo.png", mode="RGB"):
    image = Image.new(mode, size, "red" if mode == "RGB" else 1)
    if mode == "RGB":
        image.paste((0, 0, 255), (size[0] // 2, 0, size[0], size[1]))  # right half blue
    out = io.BytesIO()
    image.save(out, format=fmt)
    return SimpleUploadedFile(name, out.getvalue(), content_type=f"image/{fmt.lower()}")


def form_data(**overrides):
    data = {
        "name": "Sample Exterior Co.",
        "contact_email": "office@example.com",
        "contact_phone": "+1 555 010 0100",
        "currency": "USD",
        "links-TOTAL_FORMS": "0",
        "links-INITIAL_FORMS": "0",
        "links-MIN_NUM_FORMS": "0",
        "links-MAX_NUM_FORMS": "1000",
    }
    data.update(overrides)
    return data


class MediaTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media = tempfile.mkdtemp()
        cls.override = override_settings(MEDIA_ROOT=cls.media)
        cls.override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.override.disable()
        shutil.rmtree(cls.media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.owner = grant_role(f.user("boss", first_name="Alex", last_name="Morgan"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)


class AccessTests(MediaTestCase):
    def test_owner_only(self):
        for username, role, expected in (("rep", Role.SALES_REP, 403), ("crew", Role.CLEANER, 403)):
            grant_role(f.user(username), role)
            self.client.login(username=username, password=PASSWORD)
            self.assertEqual(self.client.get(URL).status_code, expected)
            self.assertEqual(self.client.get(reverse("core:business_export")).status_code, expected)
        self.client.logout()
        self.assertEqual(self.client.get(URL).status_code, 302)

    def test_gear_menu_links_here_for_the_owner(self):
        self.assertContains(self.client.get("/"), f'href="{URL}"')


class BusinessInfoTests(MediaTestCase):
    def test_reading_never_creates_the_row(self):
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertFalse(BusinessSettings.objects.exists())

    def test_name_contact_and_currency_save_and_show_everywhere(self):
        response = self.client.post(URL, form_data(currency="CAD"))
        self.assertRedirects(response, URL)
        business = BusinessSettings.objects.get()
        self.assertEqual(
            (business.name, business.contact_email, business.currency),
            ("Sample Exterior Co.", "office@example.com", "CAD"),
        )
        page = self.client.get("/").content.decode()
        self.assertIn("<title>Dashboard · Sample Exterior Co.</title>", page)
        self.assertIn('<span class="brand-name">Sample Exterior Co.</span>', page)
        self.assertEqual(
            self.client.get(reverse("core:manifest")).json()["name"], "Sample Exterior Co."
        )

    def test_currency_drives_money_formatting(self):
        job = f.job(f.contact(self.owner), self.owner, lines=[(Decimal("1"), Decimal("1234.50"))])
        self.assertContains(self.client.get(job.get_absolute_url()), "$1,234.50")
        self.client.post(URL, form_data(currency="CAD"))
        self.assertContains(self.client.get(job.get_absolute_url()), "CA$1,234.50")

    def test_blank_name_falls_back_to_the_install_brand(self):
        self.client.post(URL, form_data(name=""))
        self.assertContains(self.client.get("/"), '<span class="brand-name">Exterior CRM</span>')

    def test_owner_name_is_shown_read_only(self):
        self.assertContains(self.client.get(URL), 'value="Alex Morgan" readonly')


class LogoTests(MediaTestCase):
    def upload(self, file, **crop):
        return self.client.post(URL, form_data(logo_file=file, **crop))

    def stored(self):
        business = BusinessSettings.objects.get()
        with Image.open(business.logo.path) as image:
            return image.format, image.size, image.getpixel((5, 5)), image.info

    def test_crop_square_is_kept_resized_and_reencoded(self):
        self.upload(image_file(), crop_x="400", crop_y="0", crop_size="400")
        image_format, size, corner, info = self.stored()
        self.assertEqual((image_format, size), ("PNG", (400, 400)))
        self.assertEqual(corner[:3], (0, 0, 255))  # the blue right half
        self.assertNotIn("exif", info)

    def test_without_crop_the_center_square_is_used_and_large_images_shrink(self):
        self.upload(image_file((2000, 1000)))
        image_format, size, corner, _ = self.stored()
        self.assertEqual(size, (512, 512))
        self.assertEqual(corner[:3], (255, 0, 0))  # center square starts in the red half

    def test_out_of_bounds_crop_falls_back_to_center(self):
        self.upload(image_file(), crop_x="700", crop_y="0", crop_size="400")
        self.assertEqual(self.stored()[1], (400, 400))

    def test_unreadable_crop_values_still_save_a_center_crop(self):
        # The crop square comes from a hidden field, so a bad value must
        # not block the save with an error nobody can see or correct.
        response = self.upload(image_file(), crop_x="", crop_y="oops", crop_size="400")
        self.assertRedirects(response, URL)
        self.assertEqual(self.stored()[1], (400, 400))

    def test_rejects_non_images_wrong_formats_huge_files_and_image_bombs(self):
        cases = {
            "an image we can read": SimpleUploadedFile(
                "x.png", b"not an image", content_type="image/png"
            ),
            "JPEG, PNG, GIF, or WebP": image_file(fmt="BMP", name="x.bmp"),
            "over 40 megapixels": image_file((8000, 6000), mode="1"),
            "over 5 MB": SimpleUploadedFile("big.png", b"0" * (5 * 1024 * 1024 + 1)),
        }
        for message, file in cases.items():
            response = self.upload(file)
            self.assertEqual(response.status_code, 200, message)
            self.assertContains(response, message)
        self.assertFalse(BusinessSettings.objects.exists())

    def test_logo_is_served_shown_replaced_and_removed(self):
        self.assertEqual(self.client.get(reverse("core:business_logo")).status_code, 404)
        self.upload(image_file())
        first = BusinessSettings.objects.get().logo
        response = self.client.get(reverse("core:business_logo"))
        self.assertEqual((response.status_code, response["Content-Type"]), (200, "image/png"))
        self.assertIn("max-age", response["Cache-Control"])
        self.assertContains(self.client.get("/"), "brand-mark is-logo")

        self.upload(image_file((300, 300)))
        second = BusinessSettings.objects.get().logo
        self.assertNotEqual(first.name, second.name)
        self.assertFalse(first.storage.exists(first.name))  # old file cleaned up

        self.client.post(URL, form_data(remove_logo="on"))
        self.assertFalse(BusinessSettings.objects.get().logo)
        self.assertFalse(second.storage.exists(second.name))

    def test_logged_out_login_page_shows_the_logo(self):
        self.upload(image_file())
        self.client.logout()
        self.assertContains(self.client.get(reverse("users:login")), "brand-mark is-logo")


class LinkTests(MediaTestCase):
    def post_links(self, rows, initial=0):
        data = form_data(
            **{"links-TOTAL_FORMS": str(len(rows)), "links-INITIAL_FORMS": str(initial)}
        )
        for i, row in enumerate(rows):
            for key, value in row.items():
                data[f"links-{i}-{key}"] = value
        return self.client.post(URL, data)

    def test_one_per_platform_and_labeled_others(self):
        response = self.post_links(
            [
                {"platform": "website", "url": "https://example.com"},
                {"platform": "other", "label": "Angi", "url": "https://example.com/angi"},
                {"platform": "other", "label": "Thumbtack", "url": "https://example.com/tt"},
                {"platform": "", "label": "", "url": ""},  # blank row ignored
            ]
        )
        self.assertRedirects(response, URL)
        self.assertEqual(
            [link.display_label for link in BusinessLink.objects.all()],
            ["Website", "Angi", "Thumbtack"],
        )

    def test_duplicate_platform_and_unlabeled_other_are_errors(self):
        response = self.post_links(
            [
                {"platform": "website", "url": "https://example.com"},
                {"platform": "website", "url": "https://example.org"},
                {"platform": "other", "label": "", "url": "https://example.net"},
            ]
        )
        self.assertContains(response, "Only one link per platform")
        self.assertContains(response, "Give this link a label.")
        self.assertFalse(BusinessLink.objects.exists())

    def test_an_added_link_goes_last(self):
        self.post_links(
            [
                {"platform": "website", "url": "https://example.com"},
                {"platform": "facebook", "url": "https://example.com/fb"},
                {"platform": "yelp", "url": "https://example.com/yelp"},
            ]
        )
        saved = list(BusinessLink.objects.all())
        rows = [{"id": str(link.pk), "platform": link.platform, "url": link.url} for link in saved]
        rows.append({"platform": "instagram", "url": "https://example.com/ig"})
        self.post_links(rows, initial=len(saved))
        self.assertEqual(
            [link.platform for link in BusinessLink.objects.all()],
            ["website", "facebook", "yelp", "instagram"],
        )

    def test_remove_a_link(self):
        link = BusinessLink.objects.create(platform="website", url="https://example.com")
        response = self.post_links(
            [
                {
                    "id": str(link.pk),
                    "platform": "website",
                    "url": "https://example.com",
                    "DELETE": "on",
                }
            ],
            initial=1,
        )
        self.assertRedirects(response, URL)
        self.assertFalse(BusinessLink.objects.exists())


class ExportTests(MediaTestCase):
    def download(self, dataset, fmt="csv"):
        return self.client.get(reverse("core:business_export"), {"dataset": dataset, "format": fmt})

    def test_every_dataset_in_both_formats(self):
        job = f.job(f.contact(self.owner), self.owner)
        f.invoice(job)
        for dataset in (
            "customers",
            "companies",
            "jobs",
            "estimates",
            "invoices",
            "payments",
            "expenses",
            "team",
        ):
            for fmt in ("csv", "json"):
                response = self.download(dataset, fmt)
                self.assertEqual(response.status_code, 200, (dataset, fmt))
                self.assertIn(f'filename="{dataset}-', response["Content-Disposition"])
                body = b"".join(response.streaming_content).decode()
                if fmt == "json":
                    json.loads(body)

    def test_formula_cells_are_neutralized(self):
        f.contact(self.owner, '=HYPERLINK("http://x")', "@SUM(A1)")
        body = b"".join(self.download("customers").streaming_content).decode()
        row = next(r for r in csv.DictReader(io.StringIO(body)) if "HYPERLINK" in r["first_name"])
        self.assertTrue(row["first_name"].startswith("'="))
        self.assertTrue(row["last_name"].startswith("'@"))

    def test_negative_amounts_stay_numbers(self):
        # A leading "-" is a formula prefix, but a plain number isn't a
        # formula — an overpaid invoice's balance must stay numeric.
        job = f.job(f.contact(self.owner), self.owner)
        invoice = f.invoice(job, lines=[(Decimal("1"), Decimal("100"))])
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal("150"),
            received_on=date.today(),
            recorded_by=self.owner,
        )
        body = b"".join(self.download("invoices").streaming_content).decode()
        row = next(iter(csv.DictReader(io.StringIO(body))))
        self.assertFalse(row["balance"].startswith("'"))
        self.assertEqual(Decimal(row["balance"]), Decimal("-50"))

    def test_team_export_has_roles_and_no_passwords(self):
        body = b"".join(self.download("team").streaming_content).decode()
        rows = list(csv.DictReader(io.StringIO(body)))
        self.assertEqual(rows[0]["role"], "Owner")
        self.assertNotIn("password", body.lower())
        self.assertNotIn("pbkdf2", body)

    def test_unknown_dataset_or_format(self):
        self.assertEqual(self.download("secrets").status_code, 400)
        self.assertEqual(self.download("customers", "xlsx").status_code, 400)
