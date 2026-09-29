from django.test import TestCase

from apps.crm.tests._helpers import grant_role
from apps.jobs.tests import _factories as f
from apps.messaging.models import Channel, ChannelMembership, Message
from apps.messaging.services import unread_count
from apps.users.roles import Role


class UnreadCountTests(TestCase):
    def setUp(self):
        self.me = grant_role(f.user("me"), Role.CLEANER)
        self.them = grant_role(f.user("them"), Role.CLEANER)
        self.channel = Channel.objects.create(name="Test", slug="test", created_by=self.them)
        self.other_channel = Channel.objects.create(
            name="Other", slug="other", created_by=self.them
        )

    def post(self, author, channel=None):
        return Message.objects.create(
            channel=channel or self.channel, author_user=author, body="hi"
        )

    def test_counts_messages_after_my_read_marker_but_not_my_own(self):
        read = self.post(self.them)
        self.post(self.them)
        self.post(self.them)
        self.post(self.me)
        ChannelMembership.objects.create(channel=self.channel, user=self.me, last_read_message=read)
        self.assertEqual(unread_count(self.me), 2)

    def test_nothing_read_yet_means_everything_is_unread(self):
        self.post(self.them)
        self.post(self.them)
        ChannelMembership.objects.create(channel=self.channel, user=self.me)
        self.assertEqual(unread_count(self.me), 2)

    def test_uses_my_marker_not_another_members(self):
        first = self.post(self.them)
        latest = self.post(self.them)
        ChannelMembership.objects.create(
            channel=self.channel, user=self.me, last_read_message=first
        )
        ChannelMembership.objects.create(
            channel=self.channel, user=self.them, last_read_message=latest
        )
        self.assertEqual(unread_count(self.me), 1)

    def test_channels_i_cannot_read_do_not_count(self):
        sales_only = Channel.objects.create(
            name="Deals", slug="deals", audience=Channel.Audience.SALES, created_by=self.them
        )
        someone_elses_dm = Channel.objects.create(
            name="DM", slug="dm-x", kind=Channel.Kind.DIRECT, created_by=self.them
        )
        self.post(self.them, channel=sales_only)
        self.post(self.them, channel=someone_elses_dm)
        self.assertEqual(unread_count(self.me), 0)

    def test_a_readable_channel_i_never_opened_counts_in_full(self):
        self.post(self.them, channel=self.other_channel)
        self.assertEqual(unread_count(self.me), 1)
