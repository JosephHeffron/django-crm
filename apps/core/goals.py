"""Monthly goals and how the current month is doing against them
(Phase 17.5 step 4).

Every actual is a database aggregate over the calendar month so far, and
reuses the one definition of revenue in `apps/jobs/reports.py` — the
dashboard and Financials must never disagree about what a month earned.

"New customers" counts contacts added this month who are customers now;
a lead added in March and won in May counts in March, the month the
business actually gained them.
"""

from dataclasses import dataclass
from decimal import Decimal

from apps.crm.models import Contact
from apps.jobs.calendar import day_bounds
from apps.jobs.models import Job
from apps.jobs.reports import invoiced_revenue

from .models import Goal

ZERO = Decimal("0")


@dataclass(frozen=True)
class GoalProgress:
    metric: str
    label: str
    target: Decimal
    actual: Decimal
    is_money: bool

    @property
    def percent(self):
        """0-100, for the width of the bar. Over-achievement shows as a
        full bar; `is_met` says it was passed."""
        if self.target <= 0:
            return 0
        return min(100, int(self.actual / self.target * 100))

    @property
    def remaining(self):
        return max(ZERO, self.target - self.actual)

    @property
    def is_met(self):
        return self.target > 0 and self.actual >= self.target


def month_start(today):
    return today.replace(day=1)


def _actuals(today):
    first = month_start(today)
    start, end = day_bounds(first, today)
    return {
        Goal.Metric.REVENUE: invoiced_revenue(first, today),
        Goal.Metric.JOBS: Decimal(
            Job.objects.filter(
                status=Job.Status.COMPLETED, completed_at__gte=start, completed_at__lt=end
            ).count()
        ),
        Goal.Metric.CUSTOMERS: Decimal(
            Contact.objects.filter(
                status=Contact.Status.CUSTOMER, created_at__gte=start, created_at__lt=end
            ).count()
        ),
    }


def progress(today):
    """This month against each saved target, in the order of Goal.Metric.
    No targets saved yet means an empty list — the card then invites the
    Owner to set one instead of showing invented numbers."""
    goals = {goal.metric: goal for goal in Goal.objects.all()}
    if not goals:
        return []
    actuals = _actuals(today)
    return [
        GoalProgress(
            metric=metric,
            label=Goal.Metric(metric).label,
            target=goals[metric].target,
            actual=actuals[metric],
            is_money=goals[metric].is_money,
        )
        for metric in Goal.Metric.values
        if metric in goals
    ]
