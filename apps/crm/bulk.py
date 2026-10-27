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
from .models import AuditLogEntry, Task

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

    One of the two parts is always there: the caller has already
    refused an empty selection, so `changed + skipped` is at least one.
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
    """The records to act on, or the reason not to.

    Takes a **queryset**, never a list of ids, on purpose: the view has
    already narrowed it the way its own list page narrows it, so an id
    somebody posted by hand that they could not have seen is simply not
    in it.
    """
    records = list(queryset)
    if not records:
        return None, f"Tick the {noun}s you want to change first."
    if len(records) > MAX_RECORDS:
        return None, f"That is more than {MAX_RECORDS} at once. Use a smaller page."
    return records, ""


def apply_to_contacts(action, contacts, user, tag=None):
    """Returns `(changed, note, error)`.

    `note` is for the person: what happened, including what was left
    alone. `error` is set instead when nothing was attempted.
    """
    if action not in dict(CONTACT_ACTIONS):
        return _refuse("Choose what to do with them first.")
    if action in ("tag", "untag") and tag is None:
        return _refuse("Choose a tag as well.")

    # `tags` prefetched because the change log records the whole list
    # before and after, which is the difference between a history that
    # reads "tags: Spring 2027 → Spring 2027, Gutters" and one that
    # reads "tags changed".
    records, error = _selection(contacts.prefetch_related("tags"), "customer")
    if error:
        return _refuse(error)

    if action == "tag":
        changed = _retag(records, tag, user, adding=True)
        return _outcome(
            changed,
            len(records) - changed,
            "customer",
            f"Added “{tag.name}” to {{n}}.",
            "{n} already had it.",
        )
    if action == "untag":
        changed = _retag(records, tag, user, adding=False)
        return _outcome(
            changed,
            len(records) - changed,
            "customer",
            f"Removed “{tag.name}” from {{n}}.",
            "{n} did not have it.",
        )

    active = action == "reactivate"
    changed = _set_active(records, user, active=active)
    skipped = len(records) - changed
    if active:
        return _outcome(
            changed, skipped, "customer", "Reactivated {n}.", "{n} {was} already active."
        )
    return _outcome(changed, skipped, "customer", "Deactivated {n}.", "{n} {was} already inactive.")


@transaction.atomic
def _retag(contacts, tag, user, adding):
    changed = 0
    for contact in contacts:
        current = sorted(contact.tags.all(), key=lambda each: each.name)
        has_it = any(each.pk == tag.pk for each in current)
        if has_it == adding:
            continue
        before = ", ".join(each.name for each in current)
        if adding:
            contact.tags.add(tag)
            after = ", ".join(sorted([each.name for each in current] + [tag.name]))
        else:
            contact.tags.remove(tag)
            after = ", ".join(each.name for each in current if each.pk != tag.pk)
        audit.record(user, contact, AuditLogEntry.Action.UPDATED, {"tags": [before, after]})
        changed += 1
    return changed


@transaction.atomic
def _set_active(contacts, user, active):
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
    return changed


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

    records, error = _selection(tasks, "task")
    if error:
        return _refuse(error)

    status = Task.Status.COMPLETED if action == "complete" else Task.Status.CANCELLED
    changed = _set_task_status(records, user, status)
    done = "Completed {n}." if action == "complete" else "Cancelled {n}."
    return _outcome(
        changed,
        len(records) - changed,
        "task",
        done,
        "{n} {was} not pending and {was} left alone.",
    )


@transaction.atomic
def _set_task_status(tasks, user, status):
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
    return changed
