from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from guests.models import Guest, GuestAccessCredential, GuestEmailToken
from guests.services.access import (
    authenticate_guest_access,
    issue_guest_access,
    revoke_guest_access,
)
from guests.services.email_access import (
    consume_email_token,
    issue_recovery_token,
    request_email_verification,
)


class GuestAccessServiceTests(TestCase):
    def setUp(self):
        self.guest = Guest.objects.create(first_name="Marie", last_name="Dupont")

    def test_issued_secret_is_hashed_and_authenticates(self):
        issued = issue_guest_access(guest=self.guest)

        self.assertNotEqual(issued.credential.secret_hash, issued.secret)
        self.assertTrue(check_password(issued.secret, issued.credential.secret_hash))
        authenticated = authenticate_guest_access(
            selector=issued.credential.selector,
            secret=issued.secret,
        )
        self.assertEqual(authenticated.guest, self.guest)

    def test_invalid_secret_is_rejected(self):
        issued = issue_guest_access(guest=self.guest)

        authenticated = authenticate_guest_access(
            selector=issued.credential.selector,
            secret="wrong-secret",
        )

        self.assertIsNone(authenticated)

    def test_revoked_and_expired_access_are_rejected(self):
        issued = issue_guest_access(guest=self.guest)
        revoke_guest_access(credential=issued.credential)
        self.assertIsNone(
            authenticate_guest_access(
                selector=issued.credential.selector,
                secret=issued.secret,
            )
        )

        expired = issue_guest_access(
            guest=self.guest,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.assertIsNone(
            authenticate_guest_access(selector=expired.credential.selector, secret=expired.secret)
        )

    def test_rotation_revokes_previous_access(self):
        first = issue_guest_access(guest=self.guest)
        second = issue_guest_access(guest=self.guest)

        first.credential.refresh_from_db()
        self.assertIsNotNone(first.credential.revoked_at)
        self.assertIsNone(
            authenticate_guest_access(selector=first.credential.selector, secret=first.secret)
        )
        self.assertIsNotNone(
            authenticate_guest_access(selector=second.credential.selector, secret=second.secret)
        )

    @override_settings(GUEST_ACCESS_MAX_FAILURES=2, GUEST_ACCESS_LOCK_MINUTES=15)
    def test_repeated_failures_temporarily_lock_access(self):
        issued = issue_guest_access(guest=self.guest)

        authenticate_guest_access(selector=issued.credential.selector, secret="wrong-1")
        authenticate_guest_access(selector=issued.credential.selector, secret="wrong-2")

        issued.credential.refresh_from_db()
        self.assertIsNotNone(issued.credential.locked_until)
        self.assertIsNone(
            authenticate_guest_access(selector=issued.credential.selector, secret=issued.secret)
        )

    def test_companion_cannot_receive_independent_access(self):
        companion = Guest.objects.create(
            first_name="Jean",
            invitation_owner=self.guest,
        )

        with self.assertRaises(ValidationError):
            issue_guest_access(guest=companion)


class GuestEmailTokenTests(TestCase):
    def setUp(self):
        self.guest = Guest.objects.create(first_name="Marie")

    def test_email_is_only_promoted_after_verification(self):
        issued = request_email_verification(
            guest=self.guest,
            email=" Marie@Example.com ",
        )
        self.guest.refresh_from_db()
        self.assertIsNone(self.guest.email)
        self.assertEqual(self.guest.pending_email, "marie@example.com")

        token = consume_email_token(
            selector=issued.token.selector,
            secret=issued.secret,
            purpose=GuestEmailToken.Purpose.VERIFY,
        )

        self.assertIsNotNone(token)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.email, "marie@example.com")
        self.assertIsNotNone(self.guest.email_verified_at)

    def test_recovery_requires_verified_email(self):
        self.guest.email = "marie@example.com"
        self.guest.save(update_fields=["email"])

        with self.assertRaises(ValidationError):
            issue_recovery_token(guest=self.guest)

    def test_verified_email_can_issue_recovery_token(self):
        self.guest.email = "marie@example.com"
        self.guest.email_verified_at = timezone.now()
        self.guest.save(update_fields=["email", "email_verified_at"])

        issued = issue_recovery_token(guest=self.guest)

        self.assertEqual(issued.token.purpose, GuestEmailToken.Purpose.RECOVER)
        self.assertTrue(check_password(issued.secret, issued.token.secret_hash))


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class GuestAccessAdminActionTests(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            username="admin-access",
            email="admin-access@example.com",
            password="safe-test-password",
        )
        self.client.force_login(self.admin_user)
        self.primary = Guest.objects.create(first_name="Marie", last_name="Dupont")
        self.companion = Guest.objects.create(
            first_name="Jean",
            last_name="Dupont",
            invitation_owner=self.primary,
        )

    def test_companion_action_explains_that_access_belongs_to_primary(self):
        response = self.client.post(
            reverse("admin:guests_guest_changelist"),
            {
                "action": "regenerate_rsvp_access",
                "_selected_action": [self.companion.pk],
            },
            follow=True,
        )

        self.assertContains(response, "accès géré par l'invité principal Marie Dupont")
        self.assertFalse(
            GuestAccessCredential.objects.filter(guest=self.companion).exists()
        )
