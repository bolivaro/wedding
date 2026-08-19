from datetime import datetime, timezone
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from guests.models import Guest, GuestEventInvitation, WeddingEvent
from guests.services.access import issue_guest_access


OPEN_DEADLINE = datetime(2099, 9, 15, 23, 59, tzinfo=timezone.utc)
TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(
    RSVP_DEADLINE=OPEN_DEADLINE,
    SECURE_SSL_REDIRECT=False,
    STORAGES=TEST_STORAGES,
)
class RSVPViewsTests(TestCase):
    def setUp(self):
        self.guest = Guest.objects.create(
            first_name="Marie",
            last_name="Dupont",
            invitation_kind=Guest.InvitationKind.COUPLE,
            party_size_limit=2,
        )
        for event in WeddingEvent.objects.all():
            GuestEventInvitation.objects.create(
                guest=self.guest,
                event=event,
                is_eligible=event.code != WeddingEvent.Code.CITY_HALL,
            )
        self.issued = issue_guest_access(guest=self.guest)

    def login_guest(self):
        return self.client.get(
            reverse(
                "guests:access_entry",
                kwargs={
                    "selector": self.issued.credential.selector,
                    "secret": self.issued.secret,
                },
            )
        )

    def test_private_link_starts_session_then_removes_secret_from_url(self):
        response = self.login_guest()

        self.assertRedirects(response, reverse("guests:rsvp_dashboard"))
        dashboard = self.client.get(reverse("guests:rsvp_dashboard"))
        self.assertContains(dashboard, "Bonjour Marie")
        self.assertNotContains(dashboard, self.issued.secret)
        self.assertEqual(dashboard.headers["Referrer-Policy"], "same-origin")

    def test_rsvp_post_passes_real_csrf_origin_check(self):
        client = Client(enforce_csrf_checks=True)
        client.get(
            reverse(
                "guests:access_entry",
                kwargs={
                    "selector": self.issued.credential.selector,
                    "secret": self.issued.secret,
                },
            )
        )
        client.get(reverse("guests:rsvp_dashboard"))
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            reverse("guests:rsvp_respond"),
            {
                "csrfmiddlewaretoken": csrf_token,
                "status": Guest.RSVPStatus.NOT_ATTENDING,
            },
            HTTP_ORIGIN="http://testserver",
        )

        self.assertRedirects(response, reverse("guests:rsvp_dashboard"))

    def test_invalid_private_link_is_rejected(self):
        response = self.client.get(
            reverse(
                "guests:access_entry",
                kwargs={"selector": self.issued.credential.selector, "secret": "wrong"},
            )
        )

        self.assertRedirects(
            response,
            reverse("guests:access_invalid"),
            target_status_code=403,
        )

    def test_rsvp_events_are_independent_and_city_hall_is_not_editable(self):
        self.login_guest()

        response = self.client.post(
            reverse("guests:rsvp_respond"),
            {
                "status": Guest.RSVPStatus.ATTENDING,
                "event_church": Guest.RSVPStatus.ATTENDING,
                "event_reception": Guest.RSVPStatus.NOT_ATTENDING,
            },
        )

        self.assertRedirects(response, reverse("guests:rsvp_dashboard"))
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp_status, Guest.RSVPStatus.ATTENDING)
        self.assertEqual(
            self.guest.event_invitations.get(event__code=WeddingEvent.Code.CHURCH).attendance_status,
            Guest.RSVPStatus.ATTENDING,
        )
        self.assertEqual(
            self.guest.event_invitations.get(event__code=WeddingEvent.Code.RECEPTION).attendance_status,
            Guest.RSVPStatus.NOT_ATTENDING,
        )
        self.assertEqual(
            self.guest.event_invitations.get(event__code=WeddingEvent.Code.CITY_HALL).attendance_status,
            Guest.RSVPStatus.PENDING,
        )

    def test_companion_limit_is_enforced_through_view(self):
        self.login_guest()
        data = {"gender": Guest.Gender.MALE, "first_name": "Jean", "last_name": "Dupont"}

        self.client.post(reverse("guests:companion_add"), data)
        self.client.post(reverse("guests:companion_add"), data)

        self.assertEqual(self.guest.companions.filter(is_active=True).count(), 1)

    def test_ticket_preview_requires_completed_event_answers(self):
        self.login_guest()
        response = self.client.get(reverse("guests:ticket_preview"))
        self.assertRedirects(response, reverse("guests:rsvp_dashboard"))

        self.client.post(
            reverse("guests:rsvp_respond"),
            {
                "status": Guest.RSVPStatus.ATTENDING,
                "event_church": Guest.RSVPStatus.ATTENDING,
                "event_reception": Guest.RSVPStatus.ATTENDING,
            },
        )
        response = self.client.get(reverse("guests:ticket_preview"))
        self.assertContains(response, "Billets personnalisés")
        self.assertContains(response, "Marie")

    def test_public_qr_does_not_expose_identity_or_open_session(self):
        response = self.client.get(
            reverse("guests:public_qr_landing", kwargs={"token": self.guest.qr_token})
        )

        self.assertContains(response, "Invitation reconnue")
        self.assertNotContains(response, "Marie")
        dashboard = self.client.get(reverse("guests:rsvp_dashboard"))
        self.assertRedirects(
            dashboard,
            reverse("guests:access_invalid"),
            target_status_code=403,
        )

    @patch("guests.views.send_email_verification")
    def test_email_change_requires_verification(self, send_verification):
        self.login_guest()

        response = self.client.post(
            reverse("guests:email_update"),
            {"email": "marie@example.com"},
        )

        self.assertRedirects(response, reverse("guests:rsvp_dashboard"))
        self.guest.refresh_from_db()
        self.assertIsNone(self.guest.email)
        self.assertEqual(self.guest.pending_email, "marie@example.com")
        send_verification.assert_called_once()


@override_settings(
    RSVP_DEADLINE=datetime(2020, 9, 15, 23, 59, tzinfo=timezone.utc),
    SECURE_SSL_REDIRECT=False,
    STORAGES=TEST_STORAGES,
)
class ClosedRSVPViewsTests(TestCase):
    def test_direct_post_is_blocked_after_deadline(self):
        guest = Guest.objects.create(first_name="Marie")
        issued = issue_guest_access(guest=guest)
        self.client.get(
            reverse(
                "guests:access_entry",
                kwargs={"selector": issued.credential.selector, "secret": issued.secret},
            )
        )

        response = self.client.post(
            reverse("guests:rsvp_respond"),
            {"status": Guest.RSVPStatus.NOT_ATTENDING},
        )

        self.assertEqual(response.status_code, 400)
        guest.refresh_from_db()
        self.assertEqual(guest.rsvp_status, Guest.RSVPStatus.PENDING)


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class AccessRecoveryViewTests(TestCase):
    @patch("guests.views.send_access_recovery")
    def test_recovery_only_sends_for_verified_email_without_enumeration(self, send_recovery):
        Guest.objects.create(first_name="Marie", email="unverified@example.com")

        first = self.client.post(
            reverse("guests:recovery_request"),
            {"email": "unverified@example.com"},
        )
        second = self.client.post(
            reverse("guests:recovery_request"),
            {"email": "unknown@example.com"},
        )

        self.assertEqual(first.status_code, second.status_code)
        self.assertEqual(first.url, second.url)
        send_recovery.assert_not_called()
