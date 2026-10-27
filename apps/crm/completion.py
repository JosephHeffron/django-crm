"""Finishing a task: the bookkeeping that has to happen wherever one
gets marked done (Phase 22).

Moved out of `apps/crm/views.py`, where both functions had lived since
the task views were the only thing that completed a task. Phase 22's
bulk actions complete several at once from a list page, and a module
that imports the views to borrow two helpers would be a circular
import — so the rule moved to where both callers can reach it, exactly
as the change log moved to `apps/crm/audit.py` in Phase 18.5 unit 5.
A pure move: the views keep their old private names as aliases, so no
call site changed.

Why it is worth having at all, rather than three lines repeated: a view
that sets `status` and forgets `completed_at` leaves a task reading
"Completed" and counted nowhere — the same silent reporting loss
`apps/jobs/status.py` exists to prevent for jobs.
"""

from django.utils import timezone

from .followups import record_completion
from .models import Task


def sync_completed_at(task):
    """Keeps Task.completed_at in step with its status —
    set when status becomes completed, cleared otherwise (reopened to
    pending, or cancelled). Documented in docs/DATABASE_DESIGN.md's
    Lifecycle behavior as an application-layer invariant.
    """
    if task.status == Task.Status.COMPLETED:
        if task.completed_at is None:
            task.completed_at = timezone.now()
    else:
        task.completed_at = None
        task.completed_by = None


def apply_task_completion(task, user, was_completed):
    """completed_at bookkeeping plus, on a transition *into* completed,
    record_completion() — who did it, and for a follow-up the contact
    touch that resets its clock (apps/crm/followups.py). Re-saving an
    already-completed task must not log a second touch.

    A task becoming completed is stamped with **this** moment, even if
    the row already carried a date. `sync_completed_at` keeps a date it
    finds, which is right when an already-completed task is saved again
    and wrong here: a task that reached pending still holding an old
    stamp (an admin edit, say) would otherwise be reported as finished
    on that old date, by whoever just completed it. Sourcery found this
    on #181.
    """
    if task.status == Task.Status.COMPLETED and not was_completed:
        task.completed_at = None
    sync_completed_at(task)
    if task.status == Task.Status.COMPLETED and not was_completed:
        record_completion(task, user)
