"""Recording who changed what (Phase 18.5 unit 5).

Lifted out of `apps/crm/views.py`, where these three helpers had lived
since Phase 11 serving four models. Unit 5 widened the change log to
everything the app writes, and fifteen hand-rolled call sites would
have become forty.

**Explicit calls, not signals, and that is deliberate.**
`docs/DATABASE_DESIGN.md` records that only changes made through the
app's own create and update views are audited, and that leaving out
admin edits, `manage.py shell` and direct database writes is "a
deliberate scope limit, not an oversight". A `post_save` signal would
quietly overturn that: seed runs, data migrations and management
commands would all start appearing as somebody's edits. So the leverage
here is a mixin that adds one line to a view, not a mechanism that
catches writes nobody asked it to catch.

What that costs, and the page says so: a change made in the Django
admin or a shell still will not appear in the log.
"""

from django.contrib.contenttypes.models import ContentType

from .models import AuditLogEntry


def record(user, obj, action, changes=None):
    """Write one entry."""
    AuditLogEntry.objects.create(
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        user=user,
        action=action,
        changes=changes or {},
    )


def diff(previous, current, changed_fields):
    """`{field: [old, new]}` for the fields that really changed.

    A form can flag a field whose saved value didn't move — an omitted
    optional field falling back to its current value, say — and that is
    not a change worth recording. Compares values rather than their
    text, because two companies can share a name.
    """
    changes = {}
    for field in changed_fields:
        old_value = getattr(previous, field, None)
        new_value = getattr(current, field, None)
        if old_value != new_value:
            changes[field] = [
                None if old_value is None else str(old_value),
                None if new_value is None else str(new_value),
            ]
    return changes


def log_for(obj):
    """This record's own history, newest first."""
    return AuditLogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk
    ).select_related("user")


class AuditedFormMixin:
    """Record a create or an edit made through this view.

    One line on a class declaration instead of four in each
    `form_valid`.

    **Where to put it, because getting this wrong fails silently.** A
    class's own `form_valid` always beats one it inherits, so adding
    this to the bases of a class that defines `form_valid` itself does
    nothing unless that method calls `super().form_valid()`.

    Four of this project's form mixins save manually and return a
    redirect without calling super — `JobFormMixin` and its siblings —
    so for those the mixin goes on the concrete `CreateView` /
    `UpdateView`, which define no `form_valid` of their own. That is
    how it was first wired here, wrongly: the job saved, the page
    redirected, and nothing was recorded.

    A view that owns its `form_valid` and does not call super cannot
    use this at all and calls `record()` directly instead
    (`PaymentCreateView`, `JobStatusView`, `TaskCompleteView`).
    `test_the_audit_mixin_is_actually_reachable` checks the placement
    for every view that declares it.

    `audit_skip_fields` leaves out fields whose `str()` says nothing
    useful — a many-to-many manager, for instance, which prints as
    `crm.Tag.None`. Where those matter they are recorded by hand, as
    `ContactUpdateView` does for tags.
    """

    audit_skip_fields = ()

    def _audit_previous(self, form):
        """The row as it was, before the form writes over it.

        Re-read from the database rather than trusted from the
        instance: `form.instance` is the *edited* object by the time
        `form_valid` runs, so diffing against it would show no change
        at all.
        """
        if not form.instance.pk:
            return None
        return type(form.instance).objects.filter(pk=form.instance.pk).first()

    def form_valid(self, form):
        previous = self._audit_previous(form)
        response = super().form_valid(form)

        # A valid form is not a completed save. Several of this
        # project's views also validate a line-item formset inside
        # their own form_valid and re-render the page when a line is
        # wrong, leaving `self.object` unset — so reaching here says
        # only that the form was acceptable, not that anything was
        # written. Recording regardless logged a creation that never
        # happened, and crashed on the way (`record(user, None, …)`).
        saved = getattr(self, "object", None)
        if saved is None or saved.pk is None:
            return response

        if previous is None:
            record(self.request.user, saved, AuditLogEntry.Action.CREATED)
            return response
        fields = [f for f in form.changed_data if f not in self.audit_skip_fields]
        changes = diff(previous, saved, fields)
        # Nothing actually moved: an entry saying so would be noise in a
        # log whose whole job is to be readable.
        if changes:
            record(self.request.user, saved, AuditLogEntry.Action.UPDATED, changes)
        return response
