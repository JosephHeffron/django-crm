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
    for name in entry.changes:
        field = _field(model, name)
        if field is None:
            return f"“{name}” isn't a field on this record any more."
        if not isinstance(field, RESTORABLE):
            label = getattr(field, "verbose_name", name)
            return f"“{label}” isn't something that can be put back automatically."
    return None


def can_undo(entry):
    return why_not(entry) is None


def _as_stored(field, text):
    if text is None:
        return "" if not field.null else None
    if isinstance(field, models.BooleanField):
        return text.lower() in ("true", "yes", "1", "on")
    return text


def undo(entry, user):
    """Put a change back. Returns the fields restored.

    Raises CannotUndo with a readable reason — including when somebody
    has edited the record since, because undoing then would quietly
    discard their work.
    """
    reason = why_not(entry)
    if reason:
        raise CannotUndo(reason)

    record = entry.record
    model = type(record)
    restored, moved_on = {}, []
    for name, (old, new) in entry.changes.items():
        field = _field(model, name)
        current = getattr(record, name)
        if str(current) != str(new):
            moved_on.append(getattr(field, "verbose_name", name))
            continue
        restored[name] = _as_stored(field, old)
    if moved_on:
        names = ", ".join(str(name) for name in moved_on)
        raise CannotUndo(f"Somebody has changed {names} since. Undoing would lose that.")
    if not restored:
        raise CannotUndo("Nothing left to put back.")

    with transaction.atomic():
        for name, value in restored.items():
            setattr(record, name, value)
        record.save(update_fields=list(restored))
        AuditLogEntry.objects.create(
            content_type=entry.content_type,
            object_id=entry.object_id,
            user=user,
            action=AuditLogEntry.Action.UPDATED,
            changes={name: [entry.changes[name][1], entry.changes[name][0]] for name in restored},
        )
    return restored
