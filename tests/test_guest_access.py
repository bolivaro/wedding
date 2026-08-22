from datetime import date, datetime, timedelta
from unittest.mock import patch

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
from guests.services.notifications import send_email_verification


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

    @override_settings(DEBUG=False, SITE_BASE_URL="https://leslieniboli.fr")
    @patch("guests.services.notifications.send_brevo_email")
    def test_verification_email_contains_an_explicit_html_link(self, send_email):
        issued = request_email_verification(
            guest=self.guest,
            email="marie@example.com",
        )

        send_email_verification(issued_token=issued)

        kwargs = send_email.call_args.kwargs
        expected_url = (
            "https://www.leslieniboli.fr/invites/email/verify/"
            f"{issued.token.selector}/{issued.secret}/"
        )
        self.assertIn(f'href="{expected_url}"', kwargs["html_content"])
        self.assertIn(f"\n{expected_url}\n", kwargs["text_content"])
        self.assertNotIn('href="null"', kwargs["html_content"].lower())

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

    def test_admin_uses_wedding_favicon(self):
        response = self.client.get(reverse("admin:index"))

        self.assertContains(response, "website/images/favicon.svg")
        self.assertContains(response, 'rel="icon"')

    @override_settings(
        WEDDING_DATE=date(2026, 10, 17),
        RSVP_DEADLINE=datetime.fromisoformat("2026-09-15T23:59:00+02:00"),
    )
    def test_generated_access_offers_native_share_message(self):
        response = self.client.post(
            reverse("admin:guests_guest_changelist"),
            {
                "action": "regenerate_rsvp_access",
                "_selected_action": [self.primary.pk],
            },
            follow=True,
        )

        self.assertContains(response, "data-invitation-share")
        self.assertContains(response, "Partager l’invitation")
        self.assertContains(response, "Leslie &amp; Bolivar ont l’immense plaisir")
        self.assertContains(response, "17 octobre 2026")
        self.assertContains(response, "15 septembre 2026")
        self.assertContains(response, "guests/js/admin_invitation_share.js")

    def test_admin_opens_existing_rsvp_without_regenerating_access(self):
        issued = issue_guest_access(guest=self.primary, created_by=self.admin_user)
        initial_count = GuestAccessCredential.objects.filter(guest=self.primary).count()

        response = self.client.get(
            reverse(
                "admin:guests_guest_open_rsvp",
                kwargs={"guest_id": self.primary.pk},
            )
        )

        self.assertRedirects(response, reverse("guests:rsvp_dashboard"))
        self.assertEqual(
            GuestAccessCredential.objects.filter(guest=self.primary).count(),
            initial_count,
        )
        issued.credential.refresh_from_db()
        self.assertIsNone(issued.credential.revoked_at)
        dashboard = self.client.get(reverse("guests:rsvp_dashboard"))
        self.assertContains(dashboard, "Bonjour Marie")

    def test_companion_quick_access_opens_primary_rsvp(self):
        issue_guest_access(guest=self.primary, created_by=self.admin_user)

        response = self.client.get(
            reverse(
                "admin:guests_guest_open_rsvp",
                kwargs={"guest_id": self.companion.pk},
            )
        )

        self.assertRedirects(response, reverse("guests:rsvp_dashboard"))
        dashboard = self.client.get(reverse("guests:rsvp_dashboard"))
        self.assertContains(dashboard, "Bonjour Marie")

    def test_quick_access_is_unavailable_without_active_credential(self):
        response = self.client.get(
            reverse(
                "admin:guests_guest_open_rsvp",
                kwargs={"guest_id": self.primary.pk},
            ),
            follow=True,
        )

        self.assertContains(response, "aucun accès RSVP actif", status_code=200)

    def test_guest_changelist_displays_one_click_rsvp_link(self):
        issue_guest_access(guest=self.primary, created_by=self.admin_user)

        response = self.client.get(reverse("admin:guests_guest_changelist"))

        self.assertContains(response, "Ouvrir RSVP")
        self.assertContains(response, "Renouveler et partager")

    def test_renew_share_requires_confirmation_and_revokes_previous_access(self):
        previous = issue_guest_access(guest=self.primary, created_by=self.admin_user)
        renew_url = reverse(
            "admin:guests_guest_renew_share",
            kwargs={"guest_id": self.primary.pk},
        )

        confirmation = self.client.get(renew_url)

        self.assertContains(confirmation, "invalider immédiatement")
        previous.credential.refresh_from_db()
        self.assertIsNone(previous.credential.revoked_at)

        result = self.client.post(renew_url)

        self.assertContains(result, "Le nouvel accès est prêt")
        self.assertContains(result, "data-invitation-share")
        self.assertContains(result, "Partager l’invitation")
        previous.credential.refresh_from_db()
        self.assertIsNotNone(previous.credential.revoked_at)
        self.assertEqual(
            GuestAccessCredential.objects.filter(
                guest=self.primary,
                revoked_at__isnull=True,
            ).count(),
            1,
        )

    def test_guest_changelist_displays_public_qr_test_link(self):
        response = self.client.get(reverse("admin:guests_guest_changelist"))
        qr_path = reverse(
            "guests:public_qr_landing",
            kwargs={"token": self.primary.qr_token},
        )

        self.assertContains(response, "Tester le QR")
        self.assertContains(response, qr_path)

        qr_response = self.client.get(qr_path)
        self.assertContains(qr_response, "Invitation reconnue")

    def test_quick_access_requires_an_authenticated_admin(self):
        issue_guest_access(guest=self.primary, created_by=self.admin_user)
        self.client.logout()

        response = self.client.get(
            reverse(
                "admin:guests_guest_open_rsvp",
                kwargs={"guest_id": self.primary.pk},
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)
