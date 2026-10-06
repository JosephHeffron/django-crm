"""Serving the files that aren't public (Phase 18 unit 1).

`media/private/` holds job photos and people's profile pictures. Both
upload paths have said since Phase 17 that these are "served only
through a login-gated view" — this is that view. Until now Caddy served
the whole of `media/` straight from disk, so anyone with the URL could
read them without signing in.

Two rules, and they're the whole point:

- **you have to be signed in**, and
- **you have to be allowed to see the thing the file belongs to** — a
  cleaner sees photos of the jobs they're on, and not of anyone else's.

Out of scope is a 404, never a 403, matching every other scoped view in
the app: a 403 would confirm the photo exists.

Files are read through Django rather than handed to the web server with
an internal redirect. For a handful of staff and a few photos a job
that's simply not worth the second code path, and this one can be tested
here rather than only on the real machine.

Two deliberate limits, both reviewed:

- the content type is decided here, from the stored extension, rather
  than left to `FileResponse`. It guesses via `mimetypes`, which reads
  the host's MIME database — and that differs between this
  workstation, CI and the Pi. With `nosniff` the type we send is the
  type the browser uses, so it must not depend on which machine is
  serving;
- `FileResponse` streams, so a read error *after* the headers have gone
  out truncates the body instead of becoming a 500. Reading the whole
  file first would narrow that window but not close it, and it would
  cost memory on every request to catch a disk error that open()
  already catches in the common cases. `Content-Length` is set, so a
  short body is detectable by the client rather than silently wrong.
"""

from pathlib import PurePath

from django.http import FileResponse, Http404
from django.views import View

from apps.users.roles import ALL_ROLES, RoleRequiredMixin

from .access import jobs_for, quotes_for
from .models import Photo

# The type sent for each extension uploads are allowed to store.
# Explicit rather than `mimetypes.guess_type`, which consults the
# host's MIME database: `.heic` is known on this Fedora workstation and
# may not be on another machine, and with `nosniff` a wrong or missing
# type means the browser downloads the photo instead of showing it.
# `test_every_uploadable_suffix_has_a_type` keeps this in step with the
# upload allowlists in apps/jobs/models.py and apps/users/models.py.
CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def content_type_for(name):
    """The type to send for a stored file, by extension.

    Unknown extensions get `application/octet-stream` on purpose:
    claiming a type we don't know is worse than declining to guess.
    The upload paths force a known suffix, so this shouldn't arise.
    """
    return CONTENT_TYPES.get(PurePath(name).suffix.lower(), "application/octet-stream")


# What a browser should do with these: show them, never run them, and
# never hand them to another site.
HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Disposition": "inline",
    # Private: a shared cache must not keep a copy that another person's
    # request could be served from.
    "Cache-Control": "private, max-age=0, no-store",
    "Referrer-Policy": "same-origin",
}


def send_private_file(file_field, content_type=None):
    if not file_field:
        raise Http404("No file")
    try:
        handle = file_field.open("rb")
    except FileNotFoundError as error:
        # The row survives a file that's gone (a restore that missed the
        # media volume, say). Saying "not found" is the truth.
        raise Http404("The file is missing") from error
    # Any other OSError — a permission problem, a volume that isn't
    # mounted, a read error — is deliberately NOT turned into a 404.
    # Those are server faults, and dressing them as "not found" would
    # make a misconfigured media volume look to everyone like the
    # photos were simply never uploaded, with nothing in the logs
    # saying otherwise. Let it raise, so it's a 500 and gets recorded.
    response = FileResponse(handle, content_type=content_type or content_type_for(file_field.name))
    for name, value in HEADERS.items():
        response[name] = value
    return response


class PhotoView(RoleRequiredMixin, View):
    """One job or estimate photo, to someone allowed to see its job."""

    allowed_roles = ALL_ROLES

    def get(self, request, uuid, *args, **kwargs):
        photo = Photo.objects.filter(uuid=uuid).select_related("job", "quote").first()
        if photo is None or not self._may_see(request.user, photo):
            raise Http404("No such photo")
        return send_private_file(photo.image)

    def _may_see(self, user, photo):
        if photo.job_id:
            return jobs_for(user).filter(pk=photo.job_id).exists()
        if photo.quote_id:
            return quotes_for(user).filter(pk=photo.quote_id).exists()
        return False
