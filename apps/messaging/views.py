"""Team messaging pages (Phase 17 unit 3d). Plain request/response: post
with a form, see new messages on the next page load. Automatic updates
(short polling) arrive in Phase 21.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView

from apps.jobs.access import jobs_for
from apps.users.roles import ALL_ROLES, SALES_ROLES, RoleRequiredMixin, user_role

from .forms import MessageForm
from .models import Channel
from .services import channel_title, channels_for, direct_channel, mark_read, visible_channels

User = get_user_model()
PAGE_SIZE = 50


def _teammates(user):
    """Active users with a role, for starting a direct message."""
    return (
        User.objects.filter(is_active=True, groups__name__in=[r.value for r in ALL_ROLES])
        .exclude(pk=user.pk)
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


class MessagesHomeView(RoleRequiredMixin, TemplateView):
    allowed_roles = ALL_ROLES
    template_name = "messaging/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        channels = list(channels_for(user))
        for channel in channels:
            channel.title = channel_title(channel, user)
        context["public_channels"] = [c for c in channels if c.kind == Channel.Kind.PUBLIC]
        context["direct_channels"] = [c for c in channels if c.kind == Channel.Kind.DIRECT]
        context["teammates"] = _teammates(user)
        return context


class ChannelView(RoleRequiredMixin, TemplateView):
    """One channel: the latest messages (older ones via ?before=<id>),
    and a form to post. Opening it marks everything read. A channel the
    user can't read is a 404, not a 403."""

    allowed_roles = ALL_ROLES
    template_name = "messaging/channel.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and user_role(request.user) in ALL_ROLES:
            self.channel = get_object_or_404(
                visible_channels(request.user).prefetch_related("memberships__user"),
                slug=kwargs["slug"],
            )
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not request.user.has_perm("messaging.add_message"):
            raise PermissionDenied
        form = MessageForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        message = form.save(commit=False)
        message.channel = self.channel
        message.author_user = request.user
        message.save()
        mark_read(self.channel, request.user)
        return redirect(reverse("messaging:channel", args=[self.channel.slug]) + "#latest")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        page = self.channel.messages.select_related(
            "author_user", "author_contact", "ref_job", "ref_contact", "ref_quote"
        ).order_by("-pk")
        before = self.request.GET.get("before", "")
        if before.isdigit():
            page = page.filter(pk__lt=int(before))
        batch = list(page[: PAGE_SIZE + 1])
        has_older = len(batch) > PAGE_SIZE
        batch = batch[:PAGE_SIZE][::-1]  # oldest first on the page

        # Link a referenced job only for people who can open it.
        job_ids = {m.ref_job_id for m in batch if m.ref_job_id}
        visible_jobs = set(jobs_for(user).filter(pk__in=job_ids).values_list("pk", flat=True))
        for message in batch:
            message.show_job_link = message.ref_job_id in visible_jobs

        if not before:
            mark_read(self.channel, user)
        context.update(
            channel=self.channel,
            title=channel_title(self.channel, user),
            chat_messages=batch,
            older_url=f"?before={batch[0].pk}" if has_older and batch else None,
            form=kwargs.get("form") or MessageForm(),
            can_post=user.has_perm("messaging.add_message"),
            is_sales=user_role(user) in SALES_ROLES,
        )
        return context


class DirectMessageView(RoleRequiredMixin, TemplateView):
    """Opens (creating on first use) the direct channel with a teammate.
    Creating is idempotent — one channel per pair — so a plain link is
    safe."""

    allowed_roles = ALL_ROLES

    def get(self, request, *args, **kwargs):
        other = get_object_or_404(_teammates(request.user), username=kwargs["username"])
        channel = direct_channel(request.user, other)
        return redirect("messaging:channel", slug=channel.slug)
