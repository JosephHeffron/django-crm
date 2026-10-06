from django.urls import path

from . import views

app_name = "jobs"

urlpatterns = [
    path("calendar/", views.CalendarView.as_view(), name="calendar"),
    path("jobs/new/", views.JobCreateView.as_view(), name="job_create"),
    path("jobs/<int:pk>/", views.JobDetailView.as_view(), name="job_detail"),
    path("jobs/<int:pk>/edit/", views.JobUpdateView.as_view(), name="job_update"),
    path("tasks/quotes/", views.QuoteListView.as_view(), name="quote_list"),
    path("quotes/new/", views.QuoteCreateView.as_view(), name="quote_create"),
    path("quotes/<int:pk>/", views.QuoteDetailView.as_view(), name="quote_detail"),
    path("quotes/<int:pk>/edit/", views.QuoteUpdateView.as_view(), name="quote_update"),
    path("financials/", views.FinancialsView.as_view(), name="financials"),
    path("invoices/", views.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/new/", views.InvoiceCreateView.as_view(), name="invoice_create"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/edit/", views.InvoiceUpdateView.as_view(), name="invoice_update"),
    path(
        "invoices/<int:pk>/payments/new/",
        views.PaymentCreateView.as_view(),
        name="payment_create",
    ),
    path("payments/", views.PaymentListView.as_view(), name="payment_list"),
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/new/", views.ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/edit/", views.ExpenseUpdateView.as_view(), name="expense_update"),
    path("time-clock/", views.TimeClockView.as_view(), name="time_clock"),
    path("crew/assignments/", views.AssignmentsView.as_view(), name="assignments"),
    path("crew/payroll/", views.PayrollView.as_view(), name="payroll"),
    path("crew/performance/", views.PerformanceView.as_view(), name="performance"),
    path("map/", views.MapView.as_view(), name="map"),
    path("reports/", views.ReportListView.as_view(), name="report_list"),
    path("reports/<slug:slug>/", views.ReportDetailView.as_view(), name="report_detail"),
    path("reports/<slug:slug>/csv/", views.ReportCsvView.as_view(), name="report_csv"),
    path(
        "map/properties/<int:pk>/locate/",
        views.PropertyLocateView.as_view(),
        name="property_locate",
    ),
    path("settings/services/", views.ServiceListView.as_view(), name="service_list"),
    path(
        "settings/services/<int:pk>/edit/",
        views.ServiceUpdateView.as_view(),
        name="service_update",
    ),
]
