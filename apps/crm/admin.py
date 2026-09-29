from django.contrib import admin

from .models import (
    Activity,
    AuditLogEntry,
    BusinessPlan,
    Company,
    Contact,
    Deal,
    Lead,
    Note,
    PlanChecklistItem,
    Property,
    Tag,
    Task,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "owner", "is_active", "created_at")
    list_filter = ("is_active", "industry")
    search_fields = ("name", "website")


class PropertyInline(admin.TabularInline):
    model = Property
    extra = 0


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "status", "email", "lead_source", "is_active")
    list_filter = ("status", "is_active", "lead_source", "tags")
    search_fields = ("first_name", "last_name", "email", "phone")
    filter_horizontal = ("tags",)
    inlines = [PropertyInline]


class ReadOnlyLegacyAdmin(admin.ModelAdmin):
    """Lead and Deal were folded into Contact and Quote in Phase 17
    (jobs/0003) and are dropped in Phase 18 — kept visible, read-only."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Lead)
class LeadAdmin(ReadOnlyLegacyAdmin):
    list_display = ("name", "company_name", "status", "source", "owner", "created_at")
    list_filter = ("status", "source")
    search_fields = ("name", "company_name", "email")


@admin.register(Deal)
class DealAdmin(ReadOnlyLegacyAdmin):
    list_display = ("title", "company", "contact", "stage", "value", "owner", "expected_close_date")
    list_filter = ("stage",)
    search_fields = ("title",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "assigned_to", "status", "priority", "due_date")
    list_filter = ("kind", "status", "priority")
    search_fields = ("title",)


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = (
        "subject",
        "activity_type",
        "company",
        "contact",
        "lead",
        "deal",
        "created_by",
        "created_at",
    )
    list_filter = ("activity_type",)
    search_fields = ("subject", "description")

    def has_change_permission(self, request, obj=None):
        # Activities are immutable history (see docs/DATABASE_DESIGN.md).
        # Activity.save() itself now rejects updates too (see the model),
        # but hiding the change form here is still worth doing — a
        # friendlier UX than letting someone fill out an edit form and
        # only then hit a raw error on submit. Deletion is still
        # allowed (correcting a mistaken entry), editing in place is not.
        return False


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "content_type", "object_id")
    list_filter = ("action", "content_type")

    def has_add_permission(self, request):
        # Entries are only ever written by the application's own
        # Create/Update views (docs/DATABASE_DESIGN.md's "Audit history"
        # section) — an admin-created entry would misrepresent history
        # that never actually happened.
        return False

    def has_change_permission(self, request, obj=None):
        # Same reasoning as ActivityAdmin: a record of what happened
        # shouldn't itself be editable after the fact.
        return False


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ("__str__", "author", "contact", "job", "pinned", "created_at")
    list_filter = ("pinned",)
    search_fields = ("body",)


class PlanChecklistItemInline(admin.TabularInline):
    model = PlanChecklistItem
    extra = 1


@admin.register(BusinessPlan)
class BusinessPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "priority", "due_date")
    list_filter = ("status", "priority")
    search_fields = ("title",)
    inlines = [PlanChecklistItemInline]
