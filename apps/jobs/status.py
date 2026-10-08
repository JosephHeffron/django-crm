"""Changing a job's status, in one place (Phase 18.5 unit 3).

There is one rule here and it is worth stating plainly, because getting
it wrong is silent:

**Every count of finished work reads `completed_at`, not `status`.**

The dashboard, the monthly goal, Financials, a crew member's week and
the customer timeline all ask when a job was finished, not what its
status says. So a job marked Completed without that date reads
"Completed" on screen and is counted nowhere — no error, no warning,
just a job that has quietly stopped existing as far as the business
figures are concerned.

Until now the only way to change a status was the full edit form, which
stamped the date on its way through. Marking a job done from the
schedule is a second path, so the rule lives here and both paths call
it. A third path later has somewhere obvious to go, and
`test_the_edit_form_and_the_schedule_agree` fails if it doesn't.
"""

from django.utils import timezone

from .models import Job

# Offered as buttons on the schedule. Cancelled is deliberately absent:
# it is a decision with consequences for invoicing, so it stays on the
# edit form where there is room to explain.
QUICK_STATUSES = (
    (Job.Status.SCHEDULED, "New"),
    (Job.Status.IN_PROGRESS, "In progress"),
    (Job.Status.COMPLETED, "Complete"),
)


def stamp_completion(job):
    """Set or clear `completed_at` to match the status.

    Re-opening a finished job clears the date, so it stops being
    counted. Marking an already-finished job finished again leaves the
    original date alone rather than moving it to today.
    """
    if job.status == Job.Status.COMPLETED:
        if job.completed_at is None:
            job.completed_at = timezone.now()
    else:
        job.completed_at = None


def apply_status(job, status):
    """Move a job to `status`. Returns `(job, error)`.

    The same `(object, error)` shape the time clock uses, so the view
    reads the same way. An unknown status changes nothing at all.
    """
    if status not in Job.Status.values:
        return None, "That isn't a status a job can be in."
    if job.status == status:
        return job, None
    job.status = status
    stamp_completion(job)
    # `updated_at` is auto_now, and an auto_now field is only written
    # when it's named in update_fields — the same trap the undo code
    # documents.
    job.save(update_fields=["status", "completed_at", "updated_at"])
    return job, None
