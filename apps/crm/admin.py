from django.contrib import admin

from .models import Activity, Company, Contact, Deal, Lead, Task


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "industry", "owner", "is_active", "created_at")
    list_filter = ("is_active", "industry")
    search_fields = ("name", "website")


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "email", "company", "owner", "is_active")
    list_filter = ("is_active", "company")
    search_fields = ("first_name", "last_name", "email")


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "company_name", "status", "source", "owner", "created_at")
    list_filter = ("status", "source")
    search_fields = ("name", "company_name", "email")


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "contact", "stage", "value", "owner", "expected_close_date")
    list_filter = ("stage",)
    search_fields = ("title",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "assigned_to", "status", "priority", "due_date")
    list_filter = ("status", "priority")
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
