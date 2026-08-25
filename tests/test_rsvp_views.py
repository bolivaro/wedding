from datetime import datetime, timezone
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from guests.models import Guest, GuestEventInvitation, WeddingEvent
from guests.services.access import issue_guest_access
from guests.services.notifications import RSVPNotificationKind


OPEN_DEADLINE = datetime(2099, 9, 15, 23, 59, tzinfo=timezone.utc)
TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(
    RSVP_DEADLINE=OPEN_DEADLINE,
    RSVP_NOTIFICATION_EMAILS=[],
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

    def test_rsvp_dashboard_keeps_public_navigation(self):
        self.login_guest()

        response = self.client.get(reverse("guests:rsvp_dashboard"))

        self.assertContains(response, reverse("website:home"))
        self.assertContains(response, reverse("website:program"))
        self.assertContains(response, reverse("website:dress_code"))
        self.assertContains(response, reverse("website:stay"))
        self.assertContains(response, "Mon RSVP")
        self.assertContains(response, 'data-menu-toggle')
        self.assertContains(response, 'data-async-feedback')
        self.assertContains(response, 'aria-live="polite"')
        self.assertContains(response, 'data-async-dashboard="3"')
        self.assertContains(response, '?v=async-rsvp-3')
        self.assertContains(response, "Un enfant de moins de 5 ans vous accompagne ?")
        self.assertContains(response, "ne disposera malheureusement pas d’un service de garde")
        for age_label in (
            "Bébé (0–2)",
            "Enfant (3–12)",
            "Adolescent (13–17)",
            "Adulte (18–44)",
            "Adulte confirmé (45–59)",
            "Senior (60+)",
        ):
            self.assertContains(response, age_label)

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
                "age_category": Guest.AgeCategory.ADULT,
                "decline_reason": Guest.DeclineReason.PREFER_NOT_TO_SAY,
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
                "age_category": Guest.AgeCategory.ADULT,
                "event_church": Guest.RSVPStatus.ATTENDING,
                "event_cocktail": Guest.RSVPStatus.ATTENDING,
                "event_reception": Guest.RSVPStatus.NOT_ATTENDING,
            },
        )

        self.assertRedirects(response, reverse("guests:rsvp_dashboard"))
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp_status, Guest.RSVPStatus.ATTENDING)
        self.assertEqual(self.guest.age_category, Guest.AgeCategory.ADULT)
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
        self.assertEqual(
            self.guest.event_invitations.get(event__code=WeddingEvent.Code.COCKTAIL).attendance_status,
            Guest.RSVPStatus.ATTENDING,
        )

    @patch("guests.views.send_rsvp_notification")
    def test_each_positive_or_negative_rsvp_sends_a_notification(self, send_notification):
        self.login_guest()

        positive_response = self.client.post(
            reverse("guests:rsvp_respond"),
            {
                "status": Guest.RSVPStatus.ATTENDING,
                "age_category": Guest.AgeCategory.ADULT,
                "event_church": Guest.RSVPStatus.ATTENDING,
                "event_cocktail": Guest.RSVPStatus.ATTENDING,
                "event_reception": Guest.RSVPStatus.NOT_ATTENDING,
            },
        )
        negative_response = self.client.post(
            reverse("guests:rsvp_respond"),
            {
                "status": Guest.RSVPStatus.NOT_ATTENDING,
                "age_category": Guest.AgeCategory.ADULT,
                "decline_reason": Guest.DeclineReason.TRAVEL,
                "decline_message": "Le déplacement est malheureusement impossible.",
            },
        )

        self.assertRedirects(positive_response, reverse("guests:rsvp_dashboard"))
        self.assertRedirects(negative_response, reverse("guests:rsvp_dashboard"))
        self.assertEqual(send_notification.call_count, 2)
        self.assertEqual(
            [call.kwargs["guest"].rsvp_status for call in send_notification.call_args_list],
            [Guest.RSVPStatus.ATTENDING, Guest.RSVPStatus.NOT_ATTENDING],
        )
        self.assertEqual(
            [call.kwargs["notification_kind"] for call in send_notification.call_args_list],
            [RSVPNotificationKind.PROVISIONAL, RSVPNotificationKind.DECLINED],
        )
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.decline_reason, Guest.DeclineReason.TRAVEL)
        self.assertEqual(
            self.guest.decline_message,
            "Le déplacement est malheureusement impossible.",
        )

    def test_declined_rsvp_requires_a_reason(self):
        self.login_guest()

        response = self.client.post(
            reverse("guests:rsvp_respond"),
            {
                "status": Guest.RSVPStatus.NOT_ATTENDING,
                "age_category": Guest.AgeCategory.ADULT,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("Choisissez un motif", payload["fragments"]["rsvp"])
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp_status, Guest.RSVPStatus.PENDING)

    @patch("guests.views.send_rsvp_notification", side_effect=RuntimeError("Brevo indisponible"))
    def test_notification_failure_does_not_rollback_rsvp(self, send_notification):
        self.login_guest()

        response = self.client.post(
            reverse("guests:rsvp_respond"),
            {
                "status": Guest.RSVPStatus.NOT_ATTENDING,
                "age_category": Guest.AgeCategory.CONFIRMED_ADULT,
                "decline_reason": Guest.DeclineReason.PERSONAL,
            },
        )

        self.assertRedirects(response, reverse("guests:rsvp_dashboard"))
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp_status, Guest.RSVPStatus.NOT_ATTENDING)
        send_notification.assert_called_once()

    def test_rsvp_can_update_only_affected_fragments_asynchronously(self):
        self.login_guest()

        response = self.client.post(
            reverse("guests:rsvp_respond"),
            {
                "status": Guest.RSVPStatus.ATTENDING,
                "age_category": Guest.AgeCategory.ADULT,
                "event_church": Guest.RSVPStatus.ATTENDING,
                "event_cocktail": Guest.RSVPStatus.ATTENDING,
                "event_reception": Guest.RSVPStatus.NOT_ATTENDING,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(set(payload["fragments"]), {"rsvp", "ticket"})
        self.assertIn("Présent", payload["fragments"]["rsvp"])
        self.assertIn("Modifier mes disponibilités", payload["fragments"]["rsvp"])
        self.assertIn("Cérémonie", payload["fragments"]["rsvp"])
        self.assertNotIn('<details class="rsvp-editor" open', payload["fragments"]["rsvp"])
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.rsvp_status, Guest.RSVPStatus.ATTENDING)

    def test_async_rsvp_validation_preserves_submitted_component(self):
        self.login_guest()

        response = self.client.post(
            reverse("guests:rsvp_respond"),
            {
                "status": Guest.RSVPStatus.ATTENDING,
                "age_category": Guest.AgeCategory.ADULT,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(set(payload["fragments"]), {"rsvp"})
        self.assertIn("Choisissez une réponse", payload["fragments"]["rsvp"])

    def test_invalid_update_keeps_answered_rsvp_editor_open(self):
        self.login_guest()
        self.guest.rsvp_status = Guest.RSVPStatus.ATTENDING
        self.guest.rsvp_responded_at = datetime.now(timezone.utc)
        self.guest.age_category = Guest.AgeCategory.ADULT
        self.guest.save(
            update_fields=[
                "rsvp_status",
                "rsvp_responded_at",
                "age_category",
                "updated_at",
            ]
        )
        for invitation in self.guest.event_invitations.filter(is_eligible=True):
            invitation.attendance_status = Guest.RSVPStatus.ATTENDING
            invitation.save(update_fields=["attendance_status"])

        response = self.client.post(
            reverse("guests:rsvp_respond"),
            {
                "status": Guest.RSVPStatus.ATTENDING,
                "age_category": Guest.AgeCategory.ADULT,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 422)
        fragment = response.json()["fragments"]["rsvp"]
        self.assertIn('<details class="rsvp-editor" open', fragment)
        self.assertIn("Choisissez une réponse", fragment)

    def test_cocktail_has_an_independent_rsvp_question(self):
        self.login_guest()

        response = self.client.get(reverse("guests:rsvp_dashboard"))

        cocktail = WeddingEvent.objects.get(code=WeddingEvent.Code.COCKTAIL)
        self.assertTrue(cocktail.requires_rsvp)
        self.assertContains(response, 'name="event_cocktail"')

    def test_companion_limit_is_enforced_through_view(self):
        self.login_guest()
        data = {
            "gender": Guest.Gender.MALE,
            "first_name": "Jean",
            "last_name": "Dupont",
            "age_category": Guest.AgeCategory.ADULT,
        }

        self.client.post(reverse("guests:companion_add"), data)
        self.client.post(reverse("guests:companion_add"), data)

        self.assertEqual(self.guest.companions.filter(is_active=True).count(), 1)

    @patch("guests.views.send_rsvp_notification")
    def test_composition_update_keeps_initial_deadline_and_reports_new_size(self, send_notification):
        self.guest.rsvp_status = Guest.RSVPStatus.ATTENDING
        self.guest.save(update_fields=["rsvp_status", "updated_at"])
        companion = Guest.objects.create(
            first_name="Jean",
            last_name="Dupont",
            invitation_owner=self.guest,
        )
        self.login_guest()

        first_response = self.client.post(
            reverse("guests:party_composition_confirm"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(first_response.status_code, 200)
        self.assertIn("Composition confirmée : 2 personnes sur 2", first_response.json()["message"])
        self.assertIn("disabled aria-disabled=\"true\"", first_response.json()["fragments"]["companions"])
        self.guest.refresh_from_db()
        initial_deadline = self.guest.party_composition_editable_until

        removal_response = self.client.post(
            reverse("guests:companion_remove", kwargs={"companion_id": companion.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        removal_fragment = removal_response.json()["fragments"]["companions"]
        self.assertIn("Composition actuelle : 1 personne", removal_fragment)
        self.assertIn("Modification à confirmer", removal_fragment)
        self.assertNotIn("disabled aria-disabled=\"true\"", removal_fragment)
        second_response = self.client.post(
            reverse("guests:party_composition_confirm"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(second_response.status_code, 200)
        self.assertIn("Composition mise à jour : 1 personne sur 2", second_response.json()["message"])
        self.assertIn("La date limite reste fixée", second_response.json()["message"])
        self.assertIn("Confirmer la nouvelle composition", second_response.json()["fragments"]["companions"])
        self.assertIn("disabled aria-disabled=\"true\"", second_response.json()["fragments"]["companions"])
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.confirmed_party_size, 1)
        self.assertEqual(self.guest.party_composition_editable_until, initial_deadline)
        self.assertEqual(
            [call.kwargs["notification_kind"] for call in send_notification.call_args_list],
            [
                RSVPNotificationKind.COMPOSITION_CONFIRMED,
                RSVPNotificationKind.COMPOSITION_UPDATED,
            ],
        )
        self.assertEqual(send_notification.call_args_list[1].kwargs["previous_party_size"], 2)

    def test_companion_add_and_remove_can_refresh_fragments_asynchronously(self):
        self.login_guest()
        response = self.client.post(
            reverse("guests:companion_add"),
            {
                "gender": Guest.Gender.MALE,
                "first_name": "Jean",
                "last_name": "Dupont",
                "age_category": Guest.AgeCategory.CHILD,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Jean Dupont", response.json()["fragments"]["companions"])
        self.assertIn("Enfant (3–12)", response.json()["fragments"]["companions"])
        companion = self.guest.companions.get(first_name="Jean")
        self.assertEqual(companion.age_category, Guest.AgeCategory.CHILD)

        invitation_ids = list(
            companion.event_invitations.order_by("pk").values_list("pk", flat=True)
        )
        response = self.client.post(
            reverse("guests:companion_update", kwargs={"companion_id": companion.pk}),
            {
                "gender": Guest.Gender.MALE,
                "first_name": "Jean-Pierre",
                "last_name": "Dupont",
                "age_category": Guest.AgeCategory.SENIOR,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Jean-Pierre Dupont", response.json()["fragments"]["companions"])
        self.assertIn("Senior (60+)", response.json()["fragments"]["companions"])
        companion.refresh_from_db()
        self.assertEqual(companion.age_category, Guest.AgeCategory.SENIOR)
        self.assertEqual(
            list(companion.event_invitations.order_by("pk").values_list("pk", flat=True)),
            invitation_ids,
        )

        response = self.client.post(
            reverse("guests:companion_attendance", kwargs={"companion_id": companion.pk}),
            {
                "attendance_mode": Guest.AttendanceMode.CUSTOM,
                "event_church": Guest.RSVPStatus.ATTENDING,
                "event_cocktail": Guest.RSVPStatus.NOT_ATTENDING,
                "event_reception": Guest.RSVPStatus.ATTENDING,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        companion.refresh_from_db()
        self.assertEqual(companion.attendance_mode, Guest.AttendanceMode.CUSTOM)
        self.assertEqual(
            companion.event_invitations.get(event__code=WeddingEvent.Code.COCKTAIL).attendance_status,
            Guest.RSVPStatus.NOT_ATTENDING,
        )

        response = self.client.post(
            reverse("guests:companion_remove", kwargs={"companion_id": companion.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Jean Dupont", response.json()["fragments"]["companions"])
        companion.refresh_from_db()
        self.assertFalse(companion.is_active)

    def test_ticket_preview_requires_completed_event_answers(self):
        self.login_guest()
        response = self.client.get(reverse("guests:ticket_preview"))
        self.assertRedirects(response, reverse("guests:rsvp_dashboard"))

        self.client.post(
            reverse("guests:rsvp_respond"),
            {
                "status": Guest.RSVPStatus.ATTENDING,
                "age_category": Guest.AgeCategory.ADULT,
                "event_church": Guest.RSVPStatus.ATTENDING,
                "event_cocktail": Guest.RSVPStatus.ATTENDING,
                "event_reception": Guest.RSVPStatus.ATTENDING,
            },
        )
        response = self.client.get(reverse("guests:ticket_preview"))
        self.assertContains(response, "Billet de groupe")
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

    @patch("guests.views.send_email_verification")
    def test_email_verification_can_refresh_its_component_asynchronously(self, send_verification):
        self.login_guest()

        response = self.client.post(
            reverse("guests:email_update"),
            {"email": "marie@example.com"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload["fragments"]), {"email"})
        self.assertIn("marie@example.com", payload["fragments"]["email"])
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
            {
                "status": Guest.RSVPStatus.NOT_ATTENDING,
                "age_category": Guest.AgeCategory.ADULT,
            },
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
