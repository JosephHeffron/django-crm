"""Doing one thing to a page of records at once (Phase 22).

Tagging twenty customers for a spring mailing, or ticking off the eight
follow-ups you just made calls for, is otherwise twenty or eight trips
through a form.

The rules live here rather than in the views because they *are* rules
and not plumbing: which records an action is allowed to touch, what
counts as having changed, and what goes in the change log. The views
own the permission check, the scoping and the redirect.

Three things these functions are careful about, each the obvious way to
get this wrong:

- **Only what actually moved is counted.** "Deactivated 20 customers"
  when 17 were already inactive is a lie the owner would act on. Every
  action skips the records already in the state asked for, and the page
  says how many it skipped.
- **The same rule as the single-record button, not a second one.**
  Completing a task here goes through `apps/crm/completion.py`, so a
  follow-up completed from the list resets the customer's clock exactly
  as the one-click button on the task does. A bulk path with its own
  slightly different rule is how two features drift apart.
- **One change log entry per record, in the same shape** the single
  views write — so a customer's history reads the same whether they
  were deactivated on their own or as one of twenty, and the Phase 17.5
  undo keeps working on it.

Everything here is a state change, never a delete. `docs/DATABASE_DESIGN.md`
records that this app deactivates rather than deletes; a bulk delete
button would be the one control in the app able to lose twenty records
to one mis-click.
"""

from django.db import transaction

from apps.core.pagination import PER_PAGE_CHOICES

from . import audit, completion
from .models import AuditLogEntry, Contact, Task

# The largest page any list view will show, so a selection can never be
# bigger than something somebody could actually have ticked. The ids
# arrive in a form post and a post can say anything, so this is the
# guard that keeps "no unbounded record sets in memory" true here too.
MAX_RECORDS = max(PER_PAGE_CHOICES)

CONTACT_ACTIONS = (
    ("tag", "Add tag"),
    ("untag", "Remove tag"),
    ("deactivate", "Deactivate"),
    ("reactivate", "Reactivate"),
)

TASK_ACTIONS = (
    ("complete", "Mark complete"),
    ("cancel", "Cancel"),
)


def _count(number, noun):
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _was(number):
    """So the skipped half of a message reads "1 customer was already
    inactive" and "3 customers were"."""
    return "was" if number == 1 else "were"


def _outcome(changed, skipped, noun, done, already):
    """`(changed, note, "")` — the count and the sentence the page shows.

    `skipped` is counted from the records the write actually looked at,
    not from the size of the selection: a record deleted between the
    tick and the Apply should not be reported as having been left
    alone.
    """
    parts = []
    if changed:
        parts.append(done.format(n=_count(changed, noun), was=_was(changed)))
    if skipped:
        parts.append(already.format(n=_count(skipped, noun), was=_was(skipped)))
    return changed, " ".join(parts), ""


def _refuse(message):
    return 0, "", message


def _selection(queryset, noun):
    """The ids to act on, or the reason not to.

    Takes a **queryset**, never a list of ids, on purpose: the view has
    already narrowed it the way its own list page narrows it, so an id
    somebody posted by hand that they could not have seen is simply not
    in it.

    Ids rather than model instances, and one page plus one rather than
    everything matched: a posted selection is whatever was sent, so the
    cap is reached before more than a page of rows — or any of their
    tags — comes out of the database. The records themselves are read
    again, and locked, inside the transaction that changes them.
    """
    pks = list(queryset.values_list("pk", flat=True)[: MAX_RECORDS + 1])
    if not pks:
        return None, f"Tick the {noun}s you want to change first."
    if len(pks) > MAX_RECORDS:
        return None, f"That is more than {MAX_RECORDS} at once. Use a smaller page."
    return pks, ""


def apply_to_contacts(action, contacts, user, tag=None):
    """Returns `(changed, note, error)`.

    `note` is for the person: what happened, including what was left
    alone. `error` is set instead when nothing was attempted.
    """
    if action not in dict(CONTACT_ACTIONS):
        return _refuse("Choose what to do with them first.")
    if action in ("tag", "untag") and tag is None:
        return _refuse("Choose a tag as well.")

    pks, error = _selection(contacts, "customer")
    if error:
        return _refuse(error)

    if action in ("tag", "untag"):
        adding = action == "tag"
        changed, seen = _retag(pks, tag, user, adding=adding)
        done = f"Added “{tag.name}” to {{n}}." if adding else f"Removed “{tag.name}” from {{n}}."
        already = "{n} already had it." if adding else "{n} did not have it."
        return _outcome(changed, seen - changed, "customer", done, already)

    active = action == "reactivate"
    changed, seen = _set_active(pks, user, active=active)
    skipped = seen - changed
    if active:
        return _outcome(
            changed, skipped, "customer", "Reactivated {n}.", "{n} {was} already active."
        )
    return _outcome(changed, skipped, "customer", "Deactivated {n}.", "{n} {was} already inactive.")


def _locked(model, pks):
    """The records to change, locked for this transaction, in a settled
    order.

    Everything decided about a record is decided from the row read
    here, not from the copy the selection read a moment earlier. Two
    Applies at once — the same person double-clicking is the likely one
    — would otherwise both see a pending task and both complete it,
    writing two log entries and, for a follow-up, two customer
    touches. `apps/crm/undo.py` locks for the same reason, in the same
    shape.

    Ordered by primary key so that two overlapping requests take the
    rows in the same order and queue instead of deadlocking.
    """
    return list(model.objects.select_for_update().filter(pk__in=pks).order_by("pk"))


@transaction.atomic
def _retag(pks, tag, user, adding):
    """Returns `(changed, seen)`."""
    contacts = _locked(Contact, pks)
    # Read **after** the rows are locked, so a tag another request has
    # just added is seen rather than added again. One query for the lot
    # rather than one per customer, because the log entry records the
    # whole list before and after — the difference between a history
    # that reads "tags: Spring 2027 → Spring 2027, Gutters" and one
    # that reads "tags changed".
    held = {}
    links = Contact.tags.through.objects.filter(contact_id__in=pks).select_related("tag")
    for link in links:
        held.setdefault(link.contact_id, []).append((link.tag_id, link.tag.name))

    changed = 0
    for contact in contacts:
        current = sorted(held.get(contact.pk, []), key=lambda each: each[1])
        has_it = any(tag_id == tag.pk for tag_id, _ in current)
        if has_it == adding:
            continue
        before = ", ".join(name for _, name in current)
        if adding:
            contact.tags.add(tag)
            after = ", ".join(sorted([name for _, name in current] + [tag.name]))
        else:
            contact.tags.remove(tag)
            after = ", ".join(name for tag_id, name in current if tag_id != tag.pk)
        # A tag change is a change to the customer as far as the edit
        # form is concerned — it saves the tags and the row together —
        # so the row's own timestamp moves here too, rather than
        # depending on which route the change came in by.
        contact.save(update_fields=["updated_at"])
        audit.record(user, contact, AuditLogEntry.Action.UPDATED, {"tags": [before, after]})
        changed += 1
    return changed, len(contacts)


@transaction.atomic
def _set_active(pks, user, active):
    """Returns `(changed, seen)`."""
    contacts = _locked(Contact, pks)
    changed = 0
    for contact in contacts:
        if contact.is_active == active:
            continue
        was = contact.is_active
        contact.is_active = active
        contact.save(update_fields=["is_active"])
        # The same entry `ContactDeactivateView` writes, deliberately:
        # one of twenty deactivations stays as undoable from the
        # customer's own page as a single one is (apps/crm/undo.py).
        audit.record(
            user,
            contact,
            AuditLogEntry.Action.UPDATED,
            {"is_active": [str(was), str(active)]},
        )
        changed += 1
    return changed, len(contacts)


def apply_to_tasks(action, tasks, user):
    """Returns `(changed, note, error)`, as `apply_to_contacts` does.

    Only a **pending** task is touched, which is the rule
    `TaskCompleteView` already enforces for one task: without it a
    stale page could revive a cancelled task straight to completed.
    Here it matters more, because a selection of twenty is exactly
    where a cancelled one hides.
    """
    if action not in dict(TASK_ACTIONS):
        return _refuse("Choose what to do with them first.")

    pks, error = _selection(tasks, "task")
    if error:
        return _refuse(error)

    status = Task.Status.COMPLETED if action == "complete" else Task.Status.CANCELLED
    changed, seen = _set_task_status(pks, user, status)
    done = "Completed {n}." if action == "complete" else "Cancelled {n}."
    return _outcome(
        changed,
        seen - changed,
        "task",
        done,
        "{n} {was} not pending and {was} left alone.",
    )


@transaction.atomic
def _set_task_status(pks, user, status):
    """Returns `(changed, seen)`."""
    tasks = _locked(Task, pks)
    changed = 0
    for task in tasks:
        if task.status != Task.Status.PENDING:
            continue
        task.status = status
        # Goes through the shared rule rather than setting the field:
        # completing records who did it and, for a follow-up, logs the
        # customer touch that resets the repeat-service clock.
        completion.apply_task_completion(task, user, was_completed=False)
        task.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
        audit.record(
            user,
            task,
            AuditLogEntry.Action.UPDATED,
            {"status": [str(Task.Status.PENDING.label), str(Task.Status(status).label)]},
        )
        changed += 1
    return changed, len(tasks)
