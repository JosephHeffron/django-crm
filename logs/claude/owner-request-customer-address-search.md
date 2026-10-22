# OWNER REQUEST: SEARCH CUSTOMERS BY ADDRESS, AND SHOW IT

Started: 2026-10-17
Ended: 2026-10-19

PR #165, merged as `46b49b4` (`c38a2f9` the feature, `668a20b` the
Sourcery fixes). Second of the three (Phase 19.5).

## Objective

> "add searching for address in the main customer list, and have their
> address viewable after their phone number in the main list"

The only location filter was a town dropdown plus a postcode box that
needed the **whole** code, exactly — so a customer could not be found
by their street, and once found their address was one page further on.

## The decision that shaped it

The first draft added a second `pk__in` subquery for the free text.
That contradicts a rule this codebase had already settled:
`test_a_town_and_a_postcode_must_match_the_same_address` pins that
town **and** postcode must match the *same* address. Two independent
subqueries pick the other reading — a customer with a Penfield home
and an Elm St rental in Webster would match
`?town=Penfield&address=Elm`.

So `contacts_at` took a third argument instead. One queryset, so one
address has to satisfy everything asked, and `CompanyListView` keeps
working because it still passes two.

`state` and `label` are deliberately **not** searched: a two-letter
query against `state` matches every customer in a single-state book of
business, and "Home" is a label half of them share.

## The N+1 that would have shipped silently

The address column must not cost a query per row.
`prefetch_related("properties")` plus `places|first` is one extra query
regardless of row count.

**A claim in the plan was wrong and is worth recording.** I wrote that
`{{ contact.properties.first }}` re-queries per row even when
prefetched. It does not — `Property.Meta.ordering` makes the queryset
`ordered`, so `.first()` uses the cache. `.all|first` is still right,
because it reuses the one `{% with %}` the "+N more" count needs and
stays safe if that `Meta.ordering` is ever removed, but the comment in
the template now says *that* rather than the false mechanism. The
mutation run confirmed it: writing the column with `.first` survives
every test, and it is the missing prefetch that both query-count tests
catch.

## Two of my own tests were weaker than they looked

Both found by mutation, not by reading.

1. **The primary-address test passed on alphabetical luck.** It
   asserted the row shows "1 Main St" rather than "9 Second St" — true
   under `["-is_primary", "street"]` and still true under plain
   `["street"]`. Cutting `Meta.ordering` down passed. The streets are
   now named so the main address sorts **last**, and the test goes red
   when that ordering is mutated.

2. **The paging test could not fail for its stated reason** —
   Sourcery's catch. It seeded 30 matching customers and nothing else,
   so dropping the filter when building page two left the same 30 rows
   and the same count. A non-matching dozen now makes it bite:
   unfiltered the count would be 42 and page two would be full of Oak
   Dr. Verified by mutating the filter off for any request carrying
   `?page=`.

## The postcode box's retirement

`?postal=` keeps filtering though its input is gone, so old bookmarks
still work — but as first written the box read **empty** while the
results were narrowed, and pressing Filter dropped the postcode and
widened them with nothing on the page to say why. Sourcery caught that
too.

An old `?postal=` is now echoed into the address box, so the page
shows the filter in effect and hands it back as `?address=14526`,
which the free-text branch matches on `postal_code__icontains`. Not
carried as a hidden field: an invisible filter you cannot clear is
worse than one shown in a box you can edit.

## Two findings declined, with reasons

- **Trigram indexes** on street, city and postcode: speculative at
  this scale. `pg_trgm` plus three GIN indexes is an extension in a
  migration and index maintenance on every address write, for a book
  of business in the hundreds of rows on a Raspberry Pi. The
  performance rules say to index from measured query patterns. If
  address search ever gets slow, this is the fix.
- **Read skew** between the filter query and the prefetch: real in the
  literal sense, but it describes every `prefetch_related` in the
  codebase. Under READ COMMITTED the window is milliseconds and the
  symptom is one stale address for one render. Closing it means
  explicit transactions around list views — a new architectural rule
  for a cosmetic race.

## Files changed

- `apps/crm/views.py` — `contacts_at(town, postal, text)`;
  `ContactListView` prefetch, `?address=`, and the echo.
- `apps/crm/templates/crm/contact_list.html` — the address box, the
  `Address` column and cell.
- `apps/crm/tests/test_address_filter.py` — 16 tests.

## Verification

```
python manage.py test        # 1,162 pass
ruff check . && ruff format --check .
python manage.py makemigrations --check
```

16 mutations, 15 caught. The survivor (`properties.first`) is not a
defect, for the reason above.
