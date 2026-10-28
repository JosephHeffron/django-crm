"""Getting back in after forgetting a password (Phase 22.5 unit 1).

Django's own views do the work — the token, the single use, the
timeout, the "we won't say whether that address exists" behaviour. One
thing is added, and it is worth the file:

**the link in the email must point at the CRM, whichever host the
request arrived on.** Django builds it from the request's host, which
is right today because the CRM is the only host in ALLOWED_HOSTS. The
public website's booking form puts the apex and `www` in there too
(`docs/VPS_DEPLOYMENT_PLAN.md` D1), and from that moment a reset
requested through the website would email a link to
`heffronexteriorservices.com/accounts/...` — a path Caddy serves from
the static site and never proxies to Django. A dead link, in the one
email that has to work, discovered by somebody already locked out.

`CRM_SITE_HOST` pins it. Left unset, nothing changes.

`site_name` is set here too, always. Without `django.contrib.sites`
installed, Django falls back to a `RequestSite`, whose name is the
hostname — so the subject line would read "crm.example.com: set a new
password" instead of the business's name.
"""

from django.conf import settings
from django.contrib.auth import views as auth_views


class PasswordResetView(auth_views.PasswordResetView):
    """Ask for the email, send the link."""

    def form_valid(self, form):
        # `extra_email_context` is the view's own attribute, which
        # Django hands to `form.save()` and merges into the context the
        # email templates render with; `domain` is what Django's
        # `password_reset_email.html` interpolates. It is **not** a form
        # kwarg — passing it as one raises TypeError, which is how the
        # first version of this was written and what the host test
        # caught.
        context = {
            **(self.extra_email_context or {}),
            "site_name": settings.CRM_BRAND_NAME,
        }
        host = (settings.CRM_SITE_HOST or "").strip()
        if host:
            context["domain"] = host
        self.extra_email_context = context
        return super().form_valid(form)
