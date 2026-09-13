"""Regression tests for the settings changes made in
docs/SECURITY_REVIEW.md (Phase 6 unit 1)."""

from django.conf import settings
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.test import TestCase


class CsrfCookieHttpOnlyTests(TestCase):
    def test_csrf_cookie_is_httponly(self):
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)


class PasswordMinimumLengthTests(TestCase):
    def test_an_11_character_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            password_validation.validate_password("aB3xyzqwerty"[:11])

    def test_a_12_character_password_is_accepted(self):
        # Not similar to any user attribute, not a common password, not
        # entirely numeric — should pass every configured validator.
        password_validation.validate_password("Xk9-quartz-77")
