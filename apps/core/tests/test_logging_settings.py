"""Regression tests for the LOGGING configuration added in
docs/LOGGING_REVIEW.md (Phase 12 unit 2).

Django's own default logging config gates its only console handler
behind DEBUG=True, so an unhandled view exception previously logged
nowhere at all in production (DEBUG=False) — confirmed live, not just
read from Django's source, in docs/LOGGING_REVIEW.md. These tests
guard the fix: that django.* messages actually reach the "django"
logger, and that this project's own module loggers (e.g.
apps/core/views.py's health-check failure log) actually reach the
root logger — via real Python logging propagation, not by reading
settings.LOGGING and assuming it does the right thing.
"""

import logging

from django.conf import settings
from django.test import TestCase


class LoggingConfigurationTests(TestCase):
    def test_django_logger_has_an_unconditional_console_handler(self):
        # "unconditional" is the point of this fix — no
        # require_debug_true/require_debug_false filter gating it,
        # unlike Django's own default config.
        django_logger_config = settings.LOGGING["loggers"]["django"]
        self.assertIn("console", django_logger_config["handlers"])
        console_handler = settings.LOGGING["handlers"]["console"]
        self.assertNotIn("filters", console_handler)

    def test_django_request_error_reaches_the_django_logger(self):
        # This is what Django's own exception-handling middleware
        # calls for every unhandled view exception (confirmed against
        # django.utils.log.request_logger directly, in
        # docs/LOGGING_REVIEW.md) — verifying it actually propagates
        # to a logger this project configures a handler for.
        with self.assertLogs("django", level="ERROR") as captured:
            logging.getLogger("django.request").error("test unhandled exception")
        self.assertIn("test unhandled exception", captured.output[0])

    def test_an_app_logger_reaches_the_root_logger(self):
        # apps/core/views.py's health-check failure log (and any
        # future app-level logger) has no handler of its own — it
        # only reaches console via propagation to root.
        with self.assertLogs(level="ERROR") as captured:
            logging.getLogger("apps.core.views").error("test app-level error")
        self.assertIn("test app-level error", captured.output[0])

    def test_django_logger_does_not_propagate_to_root(self):
        # Verified live that omitting this caused every django.*
        # error to print twice under DEBUG=True (once via django's
        # own handler, once via root's) — this is what prevents that.
        self.assertFalse(settings.LOGGING["loggers"]["django"]["propagate"])
