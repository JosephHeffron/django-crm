"""The dashboard's setup checklist (Phase 17.5 step 4).

Every step is answered from the database, never stored as a flag, so the
list can't drift out of step with reality — delete your last service and
that step un-ticks itself. The checklist is the Owner's: these are
business-wide setup tasks nobody else can do.

It disappears once every step is done, and the Owner can dismiss it
before then (`UserProfile.onboarding_dismissed`).

Two things deliberately aren't steps, because a box nobody can tick is
worse than no box:

- inviting teammates — there's no way to add a person from the app yet
  (step 10 of the restyle brings Company Management, and it belongs here
  then);
- scheduling a first job — job creation arrives with Scheduling in step
  5.

Reviewing the service prices isn't a step either, for the opposite
reason: every install is seeded with a catalog and starting prices
(jobs migration 0002), so the box would arrive already ticked. The
dashboard mentions it as a note instead.
"""

from dataclasses import dataclass

from django.urls import reverse

from apps.crm.models import Contact

from .models import Goal


@dataclass(frozen=True)
class Step:
    label: str
    hint: str
    url: str
    done: bool


def steps(business):
    return [
        Step(
            "Name your business",
            "It replaces the default name across the app, your sign-in page, "
            "and the installed app.",
            reverse("core:business_settings"),
            bool(business.name),
        ),
        Step(
            "Add your logo",
            "Shown in the sidebar, the top bar, and on your sign-in page.",
            reverse("core:business_settings"),
            bool(business.logo),
        ),
        Step(
            "Add your contact details",
            "The email and phone number your customers should use.",
            reverse("core:business_settings"),
            bool(business.contact_email or business.contact_phone),
        ),
        Step(
            "Add your first customer",
            "Customers hold the properties you work at, their jobs, and their history.",
            reverse("crm:contact_create"),
            Contact.objects.exists(),
        ),
        Step(
            "Set a monthly goal",
            "The dashboard then tracks the month against it.",
            reverse("core:goals"),
            Goal.objects.exists(),
        ),
    ]


def checklist(business, profile):
    """The checklist for the dashboard, or None when there's nothing to
    show (all done, or dismissed)."""
    if profile is not None and profile.onboarding_dismissed:
        return None
    items = steps(business)
    done = [step for step in items if step.done]
    if len(done) == len(items):
        return None
    return {
        "steps": items,
        "done": len(done),
        "total": len(items),
        "percent": int(len(done) / len(items) * 100),
        "next": next(step for step in items if not step.done),
    }
