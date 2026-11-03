"""The two login pages, with attempts counted (ADR 0020).

`apps/users/throttle.py` holds the counting; this is only the wiring.
Both pages go through the same counters, so ten failures spread across
the two pages trip the limit just as ten on one page would — an
attacker choosing `/admin/login/` instead gains nothing.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views

from . import throttle


class LoginView(auth_views.LoginView):
    """Django's login page, refusing after too many failed attempts."""

    def post(self, request, *args, **kwargs):
        username = throttle.posted_username(request)
        if throttle.refuse(request, username):
            return throttle.too_many_response(request)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # The password was right: clear both counters before anything
        # else, so a person who mistyped a few times first is not left
        # most of the way to a lockout.
        throttle.forget(self.request, form.get_user().get_username())
        return super().form_valid(form)

    def form_invalid(self, form):
        throttle.note_failure(self.request, throttle.posted_username(self.request))
        return super().form_invalid(form)


def admin_login(request, *args, **kwargs):
    """`/admin/login/`, same counters.

    Declared before `admin/` in `config/urls.py` so it wins the match.
    `reverse("admin:login")` still resolves to this path, so nothing in
    the admin notices.

    Success is read from the **response**: the admin login redirects on
    success and re-renders the form with 200 on a wrong password.
    Reading `request.user` instead miscounted — somebody already signed
    in (a Cleaner, say) still has their own authenticated user attached
    while POSTing guesses at another account, so every failure looked
    like a success and cleared the counters instead of filling them
    (#200).
    """
    username = throttle.posted_username(request)
    if request.method == "POST" and throttle.refuse(request, username):
        return throttle.too_many_response(request)

    response = admin.site.login(request, *args, **kwargs)

    if request.method == "POST":
        if response.status_code in (301, 302):
            throttle.forget(request, username)
        else:
            throttle.note_failure(request, username)
    return response
