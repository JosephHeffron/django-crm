from django.contrib import admin

from .models import (
    Expense,
    Invoice,
    InvoiceLineItem,
    Job,
    JobAssignment,
    JobLineItem,
    Payment,
    Photo,
    Quote,
    QuoteLineItem,
    ServiceType,
)


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "default_price",
        "pricing_unit",
        "followup_interval_months",
        "tone",
        "is_active",
        "position",
    )
    list_editable = ("default_price", "followup_interval_months", "is_active", "position")
    prepopulated_fields = {"slug": ("name",)}


class QuoteLineItemInline(admin.TabularInline):
    model = QuoteLineItem
    extra = 1


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "prepared_by", "site_visit_at", "created_at")
    list_filter = ("status",)
    search_fields = ("contact__first_name", "contact__last_name")
    autocomplete_fields = ("contact",)
    inlines = [QuoteLineItemInline]


class JobLineItemInline(admin.TabularInline):
    model = JobLineItem
    extra = 1


class JobAssignmentInline(admin.TabularInline):
    model = JobAssignment
    extra = 1


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "scheduled_start", "sales_rep")
    list_filter = ("status", "primary_service_type")
    search_fields = ("contact__first_name", "contact__last_name")
    autocomplete_fields = ("contact",)
    date_hierarchy = "scheduled_start"
    inlines = [JobLineItemInline, JobAssignmentInline]


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("uuid", "kind", "job", "quote", "uploaded_by", "created_at")
    list_filter = ("kind",)


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 1


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "issued_on", "due_on")
    list_filter = ("status",)
    date_hierarchy = "issued_on"
    inlines = [InvoiceLineItemInline, PaymentInline]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "category", "amount", "description")
    list_filter = ("category",)
    date_hierarchy = "date"
