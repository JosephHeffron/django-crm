from django.contrib import admin

from .models import Channel, ChannelMembership, Message


class ChannelMembershipInline(admin.TabularInline):
    model = ChannelMembership
    extra = 0
    raw_id_fields = ("last_read_message",)


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "is_archived", "created_at")
    list_filter = ("kind", "is_archived")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ChannelMembershipInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("__str__", "channel", "author_user", "created_at")
    list_filter = ("channel",)
    search_fields = ("body",)
    raw_id_fields = ("ref_job", "ref_contact", "ref_quote")
