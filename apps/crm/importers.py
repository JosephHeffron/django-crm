"""Bringing a customer list in from a spreadsheet (Phase 22).

The other half of `apps/core/export.py`, and it reads the **same column
names that writes**, so export → edit in Excel → import back works
without renaming anything.

Four rules shape everything here:

- **It creates; it never updates.** A row that matches somebody already
  on the books is reported and left alone, not merged into them.
  Changing an existing customer stays a deliberate act on their own
  page, where the change log records who did it and undo can reach it.
- **A bad row is skipped, not fatal.** One misspelled email in 300 rows
  should not mean fixing the file and starting again — so the valid
  rows go in and the report names every line that did not, with the
  reason.
- **It is one transaction.** Either the rows that were going to import
  are all there afterwards or none of them are; a half-finished import
  nobody can see the shape of is the worst outcome.
- **Nothing is invented.** An unknown company or tag name is *reported*
  rather than created from a typo, and the customer is still imported
  without it. Columns the file has that this does not understand are
  listed, so a quietly dropped column is visible.

Deliberately not here: updating by email match, importing jobs or
quotes, and creating companies or tags. Each would be a bigger decision
than an import page should make on its own.
"""

import csv
import io
from dataclasses import dataclass, field

from django.db import transaction

from . import audit, duplicates
from .forms import ImportRowForm
from .models import AuditLogEntry, Company, Contact, Property, Tag

# A spreadsheet of customers is tens to low thousands of rows. Both caps
# are refusals with a readable message rather than silent truncation —
# the one thing worse than "too big" is importing the first 1,000 rows
# and saying nothing.
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000

# Headers this understands. The customer columns are `export.py`'s own
# names; the address ones are not, because the export writes a single
# formatted `address` string that cannot be split back into a street
# and a town reliably.
PERSON_COLUMNS = (
    "first_name",
    "last_name",
    "email",
    "phone",
    "stage",
    "lead_source",
    "preferred_contact_method",
    "title",
    "company",
    "tags",
    "notes",
)
ADDRESS_COLUMNS = ("street", "city", "state", "postal_code")
REQUIRED_COLUMNS = ("first_name", "last_name")
# Written by the export, meaningless coming back in: the importer is the
# owner, "created" is now, and a row is active because it is new.
IGNORED_COLUMNS = ("address", "owner", "active", "created", "id", "pk")

KNOWN_COLUMNS = PERSON_COLUMNS + ADDRESS_COLUMNS + IGNORED_COLUMNS


def counted(number, one, many):
    """ "1 customer" / "3 customers", for the message the page shows.

    Both words spelled out rather than an "s" stuck on the end, which
    is how the first version of this managed "0 addresss".
    """
    return f"{number} {one}" if number == 1 else f"{number} {many}"


class Problem(Exception):
    """A reason the whole file cannot be read, in words for the reader."""


def _header(name):
    """ "First Name" and "first_name" are the same column.

    A byte-order mark is not stripped here. `_decode` reads with
    `utf-8-sig`, which removes it, and doing it in both places meant a
    test of the behaviour passed with either half broken — which is
    what a mutation pass showed.
    """
    return (name or "").strip().lower().replace(" ", "_").replace("-", "_")


def _uncell(value):
    """Undo the export's spreadsheet guard.

    `apps/core/export.py` writes a leading apostrophe before any cell
    starting with =, +, -, @ so that a spreadsheet cannot run a
    customer's name as a formula. Coming back the other way that
    apostrophe belongs to nobody's name, so without this a round trip
    turns "=Smith" into "'=Smith".
    """
    if value[:1] == "'" and value[1:2] in ("=", "+", "-", "@"):
        return value[1:]
    return value


def _decode(raw):
    """Spreadsheet exports are not always UTF-8.

    Excel on Windows writes cp1252 often enough that refusing it would
    make this page useless for the files people actually have. UTF-8 is
    tried first, and `utf-8-sig` so a byte-order mark does not become
    part of the first column's name.
    """
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise Problem("That file isn't text this can read. Save it as CSV and try again.")


def _not_csv(reader, error):
    """`csv.Error` as something the page can show.

    Reachable well inside the size cap: `csv` refuses a single cell
    over 128 KB, and a 2 MB file has room for one. Without this the
    page answers a malformed file with a 500 rather than a sentence —
    CodeRabbit found it on #182.
    """
    return Problem(f"That file isn't valid CSV, near line {reader.line_num}: {error}.")


def read(upload):
    """Rows as dicts keyed by known column, plus the headers ignored.

    Raises `Problem` when nothing can be read at all — an empty file, a
    missing name column, more rows than the cap.
    """
    if upload.size > MAX_BYTES:
        raise Problem(
            f"That file is {upload.size // 1024} KB, and the limit is "
            f"{MAX_BYTES // 1024} KB. Split it and import the parts."
        )
    text = _decode(upload.read())
    reader = csv.reader(io.StringIO(text))
    try:
        raw_headers = next(reader)
    except StopIteration:
        raise Problem("That file is empty.") from None
    except csv.Error as error:
        raise _not_csv(reader, error) from None

    headers = [_header(name) for name in raw_headers]
    missing = [name for name in REQUIRED_COLUMNS if name not in headers]
    if missing:
        raise Problem(
            "The file needs a column for each of: "
            + ", ".join(REQUIRED_COLUMNS)
            + ". Missing: "
            + ", ".join(missing)
            + "."
        )
    unknown = sorted({name for name in headers if name and name not in KNOWN_COLUMNS})

    rows = []
    try:
        for line, values in enumerate(reader, start=2):
            if not any(value.strip() for value in values):
                continue  # a blank line, which spreadsheets add freely
            row = {}
            for index, name in enumerate(headers):
                if name in KNOWN_COLUMNS and index < len(values):
                    row[name] = _uncell(values[index].strip())
            rows.append((line, row))
            if len(rows) > MAX_ROWS:
                raise Problem(
                    f"That file has more than {MAX_ROWS} rows. Split it and import the parts."
                )
    except csv.Error as error:
        raise _not_csv(reader, error) from None
    if not rows:
        raise Problem("That file has a header row and nothing else.")
    return rows, unknown


@dataclass
class Planned:
    """One line of the file, and what will happen to it."""

    line: int
    values: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    duplicate: str = ""

    @property
    def name(self):
        return f"{self.values.get('first_name', '')} {self.values.get('last_name', '')}".strip()

    @property
    def importing(self):
        return not self.problems


def _as_choice(raw, choices):
    """The stored value or the label, in any case.

    The export writes `customer`; a file that has been through a
    spreadsheet by hand says `Customer`, and refusing that would be
    pedantry. Anything else is returned untouched so the row form says
    what the allowed values are.
    """
    text = (raw or "").strip().lower()
    if not text:
        return ""
    for value, label in choices:
        if text in (value.lower(), str(label).lower()):
            return value
    return raw


def _by_name(model):
    """`{lowercased name: object}` for a small reference table.

    Companies and tags are tens of rows, so one query each beats one
    query per line of the file. Nothing here creates either: a mistyped
    tag would otherwise become a real tag, and the typo would be in the
    tag list forever.
    """
    return {record.name.strip().lower(): record for record in model.objects.all()}


def _duplicate_keys(values):
    """What makes this row "the same person" as another one."""
    keys = []
    first, last = values.get("first_name", ""), values.get("last_name", "")
    if first and last:
        keys.append(("name", f"{first.lower()} {last.lower()}"))
    if values.get("email"):
        keys.append(("email", values["email"].lower()))
    number = duplicates.digits(values.get("phone", ""))
    if number:
        keys.append(("phone", number))
    return keys


def plan(rows, include_duplicates=False):
    """What each line would do, without touching the database.

    The duplicate check runs a couple of indexed queries per line. That
    is deliberate: the alternative is reading every customer into memory
    to compare in Python, which the performance rules rule out, and an
    import is a rare, deliberate thing rather than a page somebody
    loads all day.
    """
    companies = _by_name(Company)
    tags = _by_name(Tag)
    planned, seen = [], {}

    for line, row in rows:
        values = dict(row)
        for name, choices in (
            ("stage", Contact.Status.choices),
            ("lead_source", Contact.LeadSource.choices),
            ("preferred_contact_method", Contact.ContactMethod.choices),
        ):
            if name in values:
                values[name] = _as_choice(values[name], choices)

        form = ImportRowForm(values)
        if not form.is_valid():
            problems = [
                f"{field if field != '__all__' else 'the row'}: {' '.join(messages)}"
                for field, messages in form.errors.items()
            ]
            planned.append(Planned(line=line, values=values, problems=problems))
            continue

        entry = Planned(line=line, values=dict(form.cleaned_data))

        name = entry.values.pop("company", "")
        if name:
            company = companies.get(name.strip().lower())
            entry.values["company"] = company
            if company is None:
                entry.notes.append(f"no company called “{name}” — imported without one")
        else:
            entry.values["company"] = None

        wanted = [part.strip() for part in (entry.values.pop("tags", "") or "").split(",")]
        entry.values["tag_objects"] = []
        for label in [part for part in wanted if part]:
            tag = tags.get(label.lower())
            if tag is None:
                entry.notes.append(f"no tag called “{label}” — imported without it")
            else:
                entry.values["tag_objects"].append(tag)

        # The same person twice in one file. The database check below
        # cannot see this, because planning writes nothing — so without
        # this the second row would import as a second customer.
        for key in _duplicate_keys(entry.values):
            if key in seen:
                entry.duplicate = f"line {seen[key]} of this file"
                break
        for key in _duplicate_keys(entry.values):
            seen.setdefault(key, line)

        if not entry.duplicate:
            already = duplicates.likely_duplicates(
                first_name=entry.values["first_name"],
                last_name=entry.values["last_name"],
                email=entry.values["email"],
                phone=entry.values["phone"],
            ).first()
            if already is not None:
                why = duplicates.reasons(
                    already,
                    first_name=entry.values["first_name"],
                    last_name=entry.values["last_name"],
                    email=entry.values["email"],
                    phone=entry.values["phone"],
                )
                entry.duplicate = f"{already} ({', '.join(why)})"

        if entry.duplicate and not include_duplicates:
            entry.problems.append(f"already on the books: {entry.duplicate}")
        planned.append(entry)

    return planned


@transaction.atomic
def apply(planned, user):
    """Create the customers that can be created. Returns
    `(customers, addresses)`.

    One transaction on purpose: an import that half happened, with no
    way to see where it stopped, is worse than one that did not.
    """
    customers = addresses = 0
    for entry in planned:
        if not entry.importing:
            continue
        values = entry.values
        contact = Contact.objects.create(
            first_name=values["first_name"],
            last_name=values["last_name"],
            email=values["email"],
            phone=values["phone"],
            status=values["stage"] or Contact.Status.CUSTOMER,
            lead_source=values["lead_source"],
            preferred_contact_method=values["preferred_contact_method"],
            title=values["title"],
            notes=values["notes"],
            company=values["company"],
            # The person importing owns what they brought in. The
            # file's own `owner` column is ignored: it holds a name,
            # which does not identify a user account.
            owner=user,
            created_by=user,
        )
        if values["tag_objects"]:
            contact.tags.set(values["tag_objects"])
        audit.record(user, contact, AuditLogEntry.Action.CREATED)
        customers += 1

        if values["street"]:
            # Their only address, so it is their main one. Nothing is
            # geocoded here: placing an address is an explicit action
            # (apps/crm/geocoding.py), so these arrive unplaced and the
            # map page lists them as needing it.
            address = Property.objects.create(
                contact=contact,
                street=values["street"],
                city=values["city"],
                state=values["state"],
                postal_code=values["postal_code"],
                is_primary=True,
            )
            audit.record(user, address, AuditLogEntry.Action.CREATED)
            addresses += 1

    return customers, addresses
