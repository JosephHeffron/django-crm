"""Fold the retired B2B pipeline into the field-service model
(docs/decisions/0009-field-service-domain-model.md):

- Lead → Contact with status "lead" (converted leads already have a
  Contact; they only contribute their lead source). An "unqualified"
  lead becomes an inactive contact.
- Deal → Quote with one line item (service "Other", the deal's title
  and value); stage maps to quote status; tasks on the deal move to the
  quote. A company-only deal needs a person to quote: the company's
  first contact, or a placeholder contact named after the company.

Every created row is marked (Contact.legacy_lead_id, Quote.legacy_deal_id,
or the placeholder note), so the reverse removes exactly what was added.
Lead and Deal themselves are left untouched and dropped in Phase 18.
"""

from decimal import Decimal

from django.db import migrations

STAGE_TO_STATUS = {
    "prospecting": "draft",
    "qualification": "draft",
    "proposal": "sent",
    "negotiation": "sent",
    "closed_won": "accepted",
    "closed_lost": "declined",
}
PLACEHOLDER_NOTE = "Created when a company-only deal was folded into a quote (Phase 17)."


def _split_name(name):
    parts = name.strip().split(None, 1)
    first = parts[0] if parts else name
    return first[:100], (parts[1] if len(parts) > 1 else "")[:100]


def _fold_lead(apps, lead):
    Contact = apps.get_model("crm", "Contact")
    Company = apps.get_model("crm", "Company")

    if lead.converted_contact_id:
        # Already has a Contact from the old conversion workflow; it
        # only gains the lead source it was missing.
        Contact.objects.filter(pk=lead.converted_contact_id, lead_source="").update(
            lead_source=lead.source
        )
        return
    first, last = _split_name(lead.name)
    notes = lead.notes
    company = None
    if lead.company_name:
        company = Company.objects.filter(name__iexact=lead.company_name).first()
        if company is None:
            notes = f"Company: {lead.company_name}\n{notes}".strip()
    contact = Contact.objects.create(
        first_name=first,
        last_name=last,
        email=lead.email,
        phone=lead.phone,
        status="lead",
        lead_source=lead.source,
        notes=notes,
        company=company,
        is_active=lead.status != "unqualified",
        owner_id=lead.owner_id,
        created_by_id=lead.created_by_id,
        legacy_lead_id=lead.pk,
    )
    Contact.objects.filter(pk=contact.pk).update(created_at=lead.created_at)


def _deal_contact_id(apps, deal):
    """The person a folded quote is for: the deal's contact, else its
    company's first contact, else a placeholder named after the company."""
    Contact = apps.get_model("crm", "Contact")
    Company = apps.get_model("crm", "Company")

    if deal.contact_id is not None:
        return deal.contact_id
    contact = Contact.objects.filter(company_id=deal.company_id).order_by("pk").first()
    if contact is None:
        company = Company.objects.get(pk=deal.company_id)
        contact = Contact.objects.create(
            first_name=company.name[:100],
            last_name="",
            status="lead",
            company=company,
            notes=PLACEHOLDER_NOTE,
            created_by_id=deal.created_by_id,
        )
    return contact.pk


def _fold_deal(apps, deal, service):
    Contact = apps.get_model("crm", "Contact")
    Task = apps.get_model("crm", "Task")
    Quote = apps.get_model("jobs", "Quote")
    QuoteLineItem = apps.get_model("jobs", "QuoteLineItem")

    contact_id = _deal_contact_id(apps, deal)
    notes = deal.notes
    if deal.expected_close_date:
        notes = f"Expected close: {deal.expected_close_date}\n{notes}".strip()
    won = deal.stage == "closed_won"
    quote = Quote.objects.create(
        contact_id=contact_id,
        status=STAGE_TO_STATUS[deal.stage],
        prepared_by_id=deal.owner_id or deal.created_by_id,
        accepted_at=deal.closed_at if won else None,
        notes=notes,
        legacy_deal_id=deal.pk,
    )
    QuoteLineItem.objects.create(
        quote=quote,
        service_type=service,
        description=deal.title[:255],
        quantity=Decimal("1"),
        unit_price=deal.value or Decimal("0"),
    )
    Quote.objects.filter(pk=quote.pk).update(created_at=deal.created_at)
    Task.objects.filter(deal_id=deal.pk).update(quote=quote)
    if won:
        Contact.objects.filter(pk=contact_id).update(status="customer")


def fold(apps, schema_editor):
    Lead = apps.get_model("crm", "Lead")
    Deal = apps.get_model("crm", "Deal")
    ServiceType = apps.get_model("jobs", "ServiceType")

    for lead in Lead.objects.order_by("pk"):
        _fold_lead(apps, lead)
    other = ServiceType.objects.get(slug="other")
    for deal in Deal.objects.order_by("pk"):
        _fold_deal(apps, deal, other)


def _delete_by_pk(schema_editor, model, pks):
    """Delete rows by primary key without Django's deletion collector.

    During a multi-app backwards migration, Django re-renders some
    historical models but not others, so the collector can end up
    comparing two different in-memory `Quote` classes and fail with
    "Cannot query 'Quote object': Must be 'Quote' instance" — found by
    actually reversing this unit's migrations. Callers clear every known
    child first; PostgreSQL's own FK constraints then refuse the delete
    if anything else (e.g. a job created after the fold) still points
    at a row — the right outcome for a reverse migration.
    """
    if pks:
        table = schema_editor.quote_name(model._meta.db_table)
        schema_editor.execute(f"DELETE FROM {table} WHERE id = ANY(%s)", [list(pks)])


def unfold(apps, schema_editor):
    Contact = apps.get_model("crm", "Contact")
    Task = apps.get_model("crm", "Task")
    Quote = apps.get_model("jobs", "Quote")
    QuoteLineItem = apps.get_model("jobs", "QuoteLineItem")

    quote_ids = list(
        Quote.objects.filter(legacy_deal_id__isnull=False).values_list("pk", flat=True)
    )
    Task.objects.filter(quote_id__in=quote_ids).update(quote=None)
    _delete_by_pk(
        schema_editor,
        QuoteLineItem,
        QuoteLineItem.objects.filter(quote_id__in=quote_ids).values_list("pk", flat=True),
    )
    _delete_by_pk(schema_editor, Quote, quote_ids)

    folded_contacts = Contact.objects.filter(legacy_lead_id__isnull=False) | Contact.objects.filter(
        notes=PLACEHOLDER_NOTE
    )
    contact_ids = list(folded_contacts.values_list("pk", flat=True))
    Contact.tags.through.objects.filter(contact_id__in=contact_ids).delete()
    _delete_by_pk(schema_editor, Contact, contact_ids)


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0002_seed_service_catalog"),
        ("crm", "0007_field_service_task_links"),
    ]

    operations = [migrations.RunPython(fold, unfold)]
