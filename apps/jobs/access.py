"""Row-level scoping: which records a user may see (ADR 0008).

Every view that lists or fetches these records goes through these
helpers. Fetching an object outside the returned queryset must 404 —
never 403 — so a record's existence isn't revealed.

Uses `pk__in` subqueries rather than JOIN + distinct() so the returned
querysets stay safe to annotate (totals, counts) afterwards.
"""

from apps.crm.models import Contact
from apps.users.roles import OWNER_ONLY, SALES_ROLES, Role, user_role

from .models import Invoice, Job, JobAssignment, Quote


def jobs_for(user):
    role = user_role(user)
    if role in SALES_ROLES:
        return Job.objects.all()
    if role == Role.CLEANER:
        return Job.objects.filter(pk__in=JobAssignment.objects.filter(user=user).values("job_id"))
    return Job.objects.none()


def quotes_for(user):
    return Quote.objects.all() if user_role(user) in SALES_ROLES else Quote.objects.none()


def contacts_for(user):
    """Sales roles see every contact; a cleaner sees only the customers
    of jobs they're assigned to (name, phone, address for the visit)."""
    role = user_role(user)
    if role in SALES_ROLES:
        return Contact.objects.all()
    if role == Role.CLEANER:
        return Contact.objects.filter(pk__in=jobs_for(user).values("contact_id"))
    return Contact.objects.none()


def invoices_for(user):
    return Invoice.objects.all() if user_role(user) in OWNER_ONLY else Invoice.objects.none()
