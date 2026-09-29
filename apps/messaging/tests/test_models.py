from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.crm.models import Contact
from apps.messaging.models import Channel, ChannelMembership, Message

User = get_user_model()


class DefaultChannelsTests(TestCase):
    def test_team_channels_exist(self):
        self.assertEqual(
            set(Channel.objects.values_list("slug", flat=True)), {"general", "crew", "sales"}
        )
        self.assertEqual(str(Channel.objects.get(slug="crew")), "#crew")


class MessageModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("rep")
        self.general = Channel.objects.get(slug="general")

    def test_message_needs_an_author(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Message.objects.create(channel=self.general, body="who said this?")

    def test_internal_message_defaults(self):
        msg = Message.objects.create(channel=self.general, author_user=self.user, body="Hi team")
        self.assertEqual((msg.transport, msg.direction), ("internal", "internal"))

    def test_inbound_sms_shape_is_already_representable(self):
        # Phase 24 readiness: a customer can author a message on an SMS
        # channel with provider metadata — no schema change needed.
        customer = Contact.objects.create(first_name="Pat", last_name="C", created_by=self.user)
        sms = Channel.objects.create(
            name="Pat C", slug="sms-pat", kind=Channel.Kind.CUSTOMER_SMS, contact=customer
        )
        msg = Message.objects.create(
            channel=sms,
            author_contact=customer,
            body="Can you come Tuesday?",
            transport=Message.Transport.SMS,
            direction=Message.Direction.INBOUND,
            external_id="SM123",
        )
        self.assertEqual(msg.author_contact, customer)

    def test_sms_channel_requires_a_contact(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Channel.objects.create(name="x", slug="x", kind=Channel.Kind.CUSTOMER_SMS)

    def test_one_membership_per_user_per_channel(self):
        ChannelMembership.objects.create(channel=self.general, user=self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChannelMembership.objects.create(channel=self.general, user=self.user)
