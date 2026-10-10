"""Undoing a recorded change (Phase 17.5 step 10).

The audit log stores each change as `{field: [old, new]}` — as text,
because that's what it was written for: showing people what happened.
Text is enough to put a name or a phone number back, and not enough to
put a date or a linked record back without guessing. So an entry is
undoable only when every field it touched can be restored exactly, and
the page says plainly when one can't be.

Two further rules, because this writes to a customer's record:

- a field is only put back if it still holds what the change set it to.
  Somebody edited it since, and undoing would throw their work away;
- the undo is itself recorded, so the log tells the whole story rather
  than appearing to have never happened.
"""

from django.db import models, transaction

from .models import AuditLogEntry

# Fields whose stored text is the whole value, so putting it back is
# exact rather than a guess. Dates, foreign keys and many-to-many fields
# are deliberately absent: "Oct 5, 2026" and "Pat Homeowner" don't
# identify a value, they describe one.
RESTORABLE = (
    models.CharField,
    models.TextField,
    models.EmailField,
    models.URLField,
    models.SlugField,
    models.BooleanField,
)


# Undo only ever puts back a plain field on one of these four records.
#
# This is an allow-list rather than a deny-list, and that is the whole
# point. Phase 18.5 unit 5 widened the change log to cover jobs,
# estimates, invoices, payments, tasks and addresses — and `RESTORABLE`
# includes `CharField`, so without this every one of those became
# "undoable" the moment it appeared in the log. Undoing `Job.status`
# would write the status and leave `completed_at` alone, which is
# exactly the silent reporting loss `apps/jobs/status.py` exists to
# prevent: a job reading "Completed" and counted nowhere.
#
# A field-by-field deny-list would have worked for the fields that
# exist today and failed silently the next time somebody added a text
# field to Invoice. Adding a model here is a deliberate act that has to
# come with the thought about what putting its fields back would mean.
UNDOABLE_MODELS = {
    ("crm", "company"),
    ("crm", "contact"),
    ("crm", "lead"),
    ("crm", "deal"),
}


# Fields that carry other state with them: converting a lead writes a
# contact, a company and a quote, and putting the word back would say it
# never happened while all of that still exists. The log records one
# field; these changes are never one field.
LIFECYCLE_FIELDS = {
    ("crm", "lead", "status"),
    ("crm", "deal", "stage"),
    ("crm", "contact", "status"),
    ("crm", "task", "status"),
}


class CannotUndo(Exception):
    """With the reason, in words meant for the person reading it."""


def _field(model, name):
    try:
        return model._meta.get_field(name)
    except Exception:
        return None


def why_not(entry):
    """The reason this entry can't be undone, or None if it can."""
    if entry.action != AuditLogEntry.Action.UPDATED:
        return "Only edits can be undone, not records being created."
    if entry.record is None:
        return "The record this changed is gone."
    if not entry.changes:
        return "Nothing was recorded as changed."
    model = type(entry.record)
    if (model._meta.app_label, model._meta.model_name) not in UNDOABLE_MODELS:
        return (
            f"Changes to a {model._meta.verbose_name} are recorded but can't be put back "
            "from here — undoing one field of it would leave the rest of what it affects "
            "untouched. Change it on the record itself."
        )
    for name in entry.changes:
        field = _field(model, name)
        if field is None:
            return f"“{name}” isn't a field on this record any more."
        if not isinstance(field, RESTORABLE):
            label = getattr(field, "verbose_name", name)
            return f"“{label}” isn't something that can be put back automatically."
        key = (model._meta.app_label, model._meta.model_name, name)
        if key in LIFECYCLE_FIELDS:
            label = getattr(field, "verbose_name", name)
            return (
                f"“{label}” decides what else exists, so putting it back on its own "
                "would leave behind the records it created. Change it on the record itself."
            )
    return None


def can_undo(entry):
    return why_not(entry) is None


def _as_stored(field, text):
    if text is None:
        return "" if not field.null else None
    if isinstance(field, models.BooleanField):
        return text.lower() in ("true", "yes", "1", "on")
    return text


def _auto_now_fields(model):
    """Fields Django stamps on save — they only update when they're
    named in `update_fields`."""
    return [field.name for field in model._meta.fields if getattr(field, "auto_now", False)]


def undo(entry, user):
    """Put a change back. Returns the fields restored.

    Raises CannotUndo with a readable reason — including when somebody
    has edited the record since, because undoing then would quietly
    discard their work.

    The row is locked and re-read inside the transaction before anything
    is compared. Checking a copy fetched earlier would leave a gap for
    another edit to land in and be overwritten, which is the one outcome
    this whole feature exists to avoid.
    """
    reason = why_not(entry)
    if reason:
        raise CannotUndo(reason)

    model = type(entry.record)
    with transaction.atomic():
        record = model.objects.select_for_update().filter(pk=entry.object_id).first()
        if record is None:
            raise CannotUndo("The record this changed is gone.")

        restored, moved_on = {}, []
        for name, (was, became) in entry.changes.items():
            field = _field(model, name)
            if str(getattr(record, name)) != str(became):
                moved_on.append(getattr(field, "verbose_name", name))
                continue
            restored[name] = _as_stored(field, was)
        if moved_on:
            names = ", ".join(str(name) for name in moved_on)
            raise CannotUndo(f"Somebody has changed {names} since. Undoing would lose that.")
        if not restored:
            raise CannotUndo("Nothing left to put back.")

        for name, value in restored.items():
            setattr(record, name, value)
        record.save(update_fields=list(restored) + _auto_now_fields(model))
        AuditLogEntry.objects.create(
            content_type=entry.content_type,
            object_id=entry.object_id,
            user=user,
            action=AuditLogEntry.Action.UPDATED,
            changes={name: [entry.changes[name][1], entry.changes[name][0]] for name in restored},
        )
    return restored
