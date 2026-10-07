from django.test import TestCase
from django.urls import reverse

from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.messaging.models import Channel, ChannelMembership, Message
from apps.messaging.services import channels_for, unread_count
from apps.messaging.views import PAGE_SIZE
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"


class MessagingTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss", first_name="Olivia"), Role.OWNER)
        self.rep = grant_role(f.user("rep", first_name="Sam"), Role.SALES_REP)
        self.crew = grant_role(f.user("crew", first_name="Casey"), Role.CLEANER)
        self.general = Channel.objects.get(slug="general")
        self.sales = Channel.objects.get(slug="sales")

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)

    def post_message(self, channel, author, body="hi", **extra):
        return Message.objects.create(channel=channel, author_user=author, body=body, **extra)


class ChannelAudienceTests(MessagingTestCase):
    def test_sales_channel_is_sales_only_after_migration(self):
        self.assertEqual(self.sales.audience, Channel.Audience.SALES)
        self.assertEqual(self.general.audience, Channel.Audience.EVERYONE)

    def test_cleaner_never_sees_sales_talk(self):
        self.post_message(self.sales, self.rep, "Pricing for Pat")
        self.post_message(self.general, self.rep, "Team lunch")
        self.login(self.crew)
        home = self.client.get(reverse("messaging:home"))
        self.assertNotContains(home, "#sales")
        self.assertContains(home, "#general")
        self.assertEqual(
            self.client.get(reverse("messaging:channel", args=["sales"])).status_code, 404
        )
        self.assertEqual(unread_count(self.crew), 1)  # only #general

    def test_sales_roles_see_sales(self):
        self.login(self.rep)
        self.assertEqual(
            self.client.get(reverse("messaging:channel", args=["sales"])).status_code, 200
        )

    def test_no_role_is_refused(self):
        f.user("nobody")
        self.client.login(username="nobody", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("messaging:home")).status_code, 403)


class ChannelPageTests(MessagingTestCase):
    def test_opening_marks_read_and_the_badge_clears(self):
        self.post_message(self.general, self.rep)
        self.post_message(self.general, self.rep)
        self.login(self.crew)
        self.assertContains(self.client.get(reverse("core:index")), 'class="nav-badge">2<')
        self.client.get(reverse("messaging:channel", args=["general"]))
        self.assertEqual(unread_count(self.crew), 0)
        self.assertNotContains(self.client.get(reverse("core:index")), 'class="nav-badge"')

    def test_posting(self):
        self.login(self.crew)
        url = reverse("messaging:channel", args=["general"])
        response = self.client.post(url, {"body": "  Running late  "})
        self.assertRedirects(response, url + "#latest", fetch_redirect_response=False)
        message = Message.objects.get(channel=self.general)
        self.assertEqual((message.body, message.author_user), ("Running late", self.crew))
        self.assertEqual(
            ChannelMembership.objects.get(channel=self.general, user=self.crew).last_read_message,
            message,
        )

    def test_blank_message_is_a_form_error(self):
        self.login(self.crew)
        response = self.client.post(reverse("messaging:channel", args=["general"]), {"body": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Message.objects.exists())

    def test_older_messages_page_back(self):
        for i in range(PAGE_SIZE + 5):
            self.post_message(self.general, self.rep, f"m{i}")
        self.login(self.crew)
        url = reverse("messaging:channel", args=["general"])
        first = self.client.get(url)
        shown = first.context["chat_messages"]
        # Newest first, so the latest message leads the page.
        self.assertEqual((len(shown), shown[0].body), (PAGE_SIZE, f"m{PAGE_SIZE + 4}"))
        older = self.client.get(url + first.context["older_url"])
        # And the page back carries on downwards, still newest first.
        self.assertEqual(
            [m.body for m in older.context["chat_messages"]],
            [f"m{i}" for i in reversed(range(5))],
        )
        self.assertIsNone(older.context["older_url"])

    def test_paging_back_does_not_repeat_the_page(self):
        """`?before=` has to mean "older than the oldest one shown".

        Taking it from the first of the batch instead of the last would
        page back from the *newest* message and serve the same rows for
        ever, which is what newest-first ordering makes easy to get
        wrong.
        """
        for i in range(PAGE_SIZE * 2):
            self.post_message(self.general, self.rep, f"m{i}")
        self.login(self.crew)
        url = reverse("messaging:channel", args=["general"])
        first = self.client.get(url)
        second = self.client.get(url + first.context["older_url"])
        on_first = {m.pk for m in first.context["chat_messages"]}
        on_second = {m.pk for m in second.context["chat_messages"]}
        self.assertEqual(on_first & on_second, set())
        self.assertEqual(len(on_first | on_second), PAGE_SIZE * 2)

    def test_the_newest_message_is_the_one_the_anchor_lands_on(self):
        # Distinctive wording: short markers like "m1" also occur in the
        # surrounding page markup, which made an earlier version of this
        # test pass on a coincidence.
        for body in ("firstmessagehere", "secondmessagehere", "thirdmessagehere"):
            self.post_message(self.general, self.rep, body)
        self.login(self.crew)
        page = self.client.get(reverse("messaging:channel", args=["general"])).content.decode()
        newest, oldest = page.index("thirdmessagehere"), page.index("firstmessagehere")
        self.assertLess(newest, oldest, "the newest message should be rendered first")
        # The send redirect goes to #latest, so that id has to sit on the
        # newest message rather than the last one rendered.
        self.assertLess(page.index('id="latest"'), newest)
        self.assertGreater(page.index('id="latest"'), page.index("chat-list"))

    def test_the_box_to_write_in_comes_before_the_messages(self):
        self.post_message(self.general, self.rep, "hello")
        self.login(self.rep)
        body = self.client.get(reverse("messaging:channel", args=["general"])).content.decode()
        self.assertLess(body.index('class="card chat-form"'), body.index("chat-list"))

    def test_job_reference_links_only_for_people_who_can_open_the_job(self):
        job = f.job(f.contact(self.owner), self.owner)
        self.post_message(Channel.objects.get(slug="crew"), self.owner, "See job", ref_job=job)
        self.login(self.crew)
        url = reverse("messaging:channel", args=["crew"])
        self.assertNotContains(self.client.get(url), job.get_absolute_url())
        f.assign(job, self.crew)
        self.assertContains(self.client.get(url), job.get_absolute_url())


class DirectMessageTests(MessagingTestCase):
    def test_one_channel_per_pair_members_only(self):
        self.login(self.crew)
        first = self.client.get(reverse("messaging:direct", args=["rep"]))
        channel = Channel.objects.get(kind=Channel.Kind.DIRECT)
        self.assertRedirects(first, reverse("messaging:channel", args=[channel.slug]))
        self.login(self.rep)
        self.client.get(reverse("messaging:direct", args=["crew"]))
        self.assertEqual(Channel.objects.filter(kind=Channel.Kind.DIRECT).count(), 1)
        self.assertContains(
            self.client.get(reverse("messaging:channel", args=[channel.slug])), "Casey"
        )

        self.login(self.owner)  # not a member — even the Owner
        self.assertEqual(
            self.client.get(reverse("messaging:channel", args=[channel.slug])).status_code, 404
        )

    def test_cannot_message_yourself_or_someone_without_a_role(self):
        f.user("nobody")
        self.login(self.crew)
        for username in ("crew", "nobody", "ghost"):
            self.assertEqual(
                self.client.get(reverse("messaging:direct", args=[username])).status_code,
                404,
                username,
            )

    def test_a_superuser_outside_the_owner_group_can_be_messaged(self):
        f.user("admin", is_superuser=True, first_name="Admin")
        self.login(self.crew)
        self.assertContains(
            self.client.get(reverse("messaging:home")), reverse("messaging:direct", args=["admin"])
        )
        response = self.client.get(reverse("messaging:direct", args=["admin"]))
        self.assertEqual(response.status_code, 302)

    def test_per_channel_unread_uses_my_marker(self):
        seen = self.post_message(self.general, self.rep)
        self.post_message(self.general, self.rep)
        self.post_message(self.general, self.crew)  # my own doesn't count
        ChannelMembership.objects.create(
            channel=self.general, user=self.crew, last_read_message=seen
        )
        by_slug = {c.slug: c.unread for c in channels_for(self.crew)}
        self.assertEqual(by_slug["general"], 1)
        self.assertNotIn("sales", by_slug)
