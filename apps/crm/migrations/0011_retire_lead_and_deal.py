"""Retire the Lead and Deal models without touching the database.

Phase 18 unit 5. Phase 17 folded every Lead into a Contact and every
Deal into a Quote (`jobs/0003_fold_leads_and_deals`), leaving the two
models read-only in the admin and their pages reachable only by typed
URL. This removes the code.

**Nothing in this migration changes the database.** `crm_lead` and
`crm_deal` keep their rows, indexes and constraints; `crm_task.deal_id`
and `crm_activity.lead_id`/`deal_id` keep their columns. Django simply
stops knowing about any of it. The roadmap called for removal and
`CLAUDE.md` forbids dropping tables in production; those are not the
same instruction, so the choice was the owner's, and this is what they
chose. Deploying this destroys nothing and `migrate crm 0010` undoes it
exactly.

Dropping the three now-dead pointer columns was drafted and then
abandoned, which is worth recording because it looked obviously right.
They are empty (checked: 0 rows in development point at a lead or a
deal, as expected after the fold re-pointed every task at its quote)
and three dead foreign keys on two busy tables are clutter. But
`jobs/0003`'s fold reads `crm_task.deal_id` to re-point those tasks,
so dropping the column breaks the Phase 17 rollback and the nineteen
tests that cover it. Three always-NULL columns are the cheaper of the
two prices. Dropping them is a separate decision for a day when
reversing Phase 17 is off the table.

All three are `null=True`, so removing them from the state alone is
safe: the ORM stops naming them in SELECT and in INSERT, and PostgreSQL
fills them with NULL.

One consequence worth knowing. `crm_lead` keeps its own foreign keys to
`crm_company` and `crm_contact`, now invisible to Django. A foreign key
only blocks a delete when a referencing row exists, and `crm_lead` has
none, so nothing can be blocked by it. It is also moot in practice:
this app never hard-deletes a company or a contact, it deactivates them.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0010_auditlog_recent_index"),
        # Ordering insurance, and it was earned. An earlier draft of
        # this migration really did drop `crm_task.deal_id`, which
        # `jobs/0003`'s fold reads — and nothing in the graph ordered
        # the two, so Django's topological sort put this one *first* and
        # every build of a fresh database, the CI test database
        # included, failed in the fold with "column deal_id does not
        # exist". The drop is gone, but the rule it taught stands:
        # Lead and Deal must not leave until the migration that folds
        # them has run. Keeping this line means the hazard cannot come
        # back if someone later fills in `database_operations`.
        ("jobs", "0003_fold_leads_and_deals"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                # The pointer fields go first: a foreign key cannot
                # outlive the model it points at, even in state.
                migrations.RemoveField(model_name="task", name="deal"),
                migrations.RemoveField(model_name="activity", name="deal"),
                migrations.RemoveField(model_name="activity", name="lead"),
                migrations.RemoveIndex(model_name="deal", name="crm_deal_stage_a31061_idx"),
                migrations.RemoveIndex(model_name="deal", name="crm_deal_owner_i_503b4b_idx"),
                migrations.RemoveIndex(model_name="deal", name="crm_deal_expecte_bc08a6_idx"),
                migrations.RemoveConstraint(model_name="deal", name="deal_has_company_or_contact"),
                migrations.RemoveConstraint(
                    model_name="deal", name="deal_probability_between_0_and_100"
                ),
                migrations.RemoveIndex(model_name="lead", name="crm_lead_status_2c1bc7_idx"),
                migrations.RemoveIndex(model_name="lead", name="crm_lead_owner_i_ecc77c_idx"),
                migrations.RemoveIndex(model_name="lead", name="crm_lead_created_d9bbc3_idx"),
                migrations.RemoveField(model_name="lead", name="converted_company"),
                migrations.RemoveField(model_name="lead", name="converted_contact"),
                migrations.RemoveField(model_name="lead", name="converted_deal"),
                migrations.RemoveField(model_name="lead", name="created_by"),
                migrations.RemoveField(model_name="lead", name="owner"),
                migrations.DeleteModel(name="Deal"),
                migrations.DeleteModel(name="Lead"),
            ],
        ),
    ]
