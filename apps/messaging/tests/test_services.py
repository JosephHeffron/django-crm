from django.test import TestCase

from apps.jobs.tests import _factories as f
from apps.messaging.models import Channel, ChannelMembership, Message
from apps.messaging.services import unread_count


class UnreadCountTests(TestCase):
    def setUp(self):
        self.me = f.user("me")
        self.them = f.user("them")
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

    def test_channels_i_am_not_in_do_not_count(self):
        self.post(self.them, channel=self.other_channel)
        self.assertEqual(unread_count(self.me), 0)
