from datetime import datetime, timedelta, timezone

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from guests.models import Guest, GuestEventInvitation, WeddingEvent
from guests.services.capacity import demographic_statistics, event_capacity_snapshot
from guests.services.companions import update_companion_attendance
from guests.services.composition import confirm_party_composition


RSVP_DEADLINE = datetime(2026, 9, 15, 21, 59, 59, tzinfo=timezone.utc)


@override_settings(RSVP_DEADLINE=RSVP_DEADLINE, RSVP_COMPOSITION_EDIT_DAYS=3)
class PartyCompositionTests(TestCase):
    def setUp(self):
        self.primary = Guest.objects.create(
            first_name="Marie",
            invitation_kind=Guest.InvitationKind.COUPLE,
            party_size_limit=2,
            rsvp_status=Guest.RSVPStatus.ATTENDING,
        )

    def test_edit_window_is_capped_by_global_rsvp_deadline(self):
        confirmation_time = RSVP_DEADLINE - timedelta(days=2)

        confirmed = confirm_party_composition(
            primary_guest=self.primary,
            at=confirmation_time,
        )

        self.assertEqual(confirmed.confirmed_party_size, 1)
        self.assertEqual(confirmed.party_composition_editable_until, RSVP_DEADLINE)

    def test_come_alone_soft_deactivates_existing_companion(self):
        companion = Guest.objects.create(
            first_name="Jean",
            invitation_owner=self.primary,
            rsvp_status=Guest.RSVPStatus.ATTENDING,
        )
        event = WeddingEvent.objects.get(code=WeddingEvent.Code.RECEPTION)
        invitation = GuestEventInvitation.objects.create(
            guest=companion,
            event=event,
            attendance_status=Guest.RSVPStatus.ATTENDING,
        )

        confirm_party_composition(
            primary_guest=self.primary,
            come_alone=True,
            at=RSVP_DEADLINE - timedelta(days=4),
        )

        companion.refresh_from_db()
        invitation.refresh_from_db()
        self.assertFalse(companion.is_active)
        self.assertEqual(invitation.attendance_status, Guest.RSVPStatus.NOT_ATTENDING)
        self.primary.refresh_from_db()
        self.assertEqual(self.primary.confirmed_party_size, 1)


class CapacityAndAttendanceTests(TestCase):
    def setUp(self):
        self.event = WeddingEvent.objects.get(code=WeddingEvent.Code.RECEPTION)
        self.event.attendance_change_deadline = datetime(2099, 10, 16, 21, 59, tzinfo=timezone.utc)
        self.event.save(update_fields=["attendance_change_deadline"])
        self.primary = Guest.objects.create(first_name="Marie")
        self.companion = Guest.objects.create(
            first_name="Jean",
            invitation_owner=self.primary,
            age_category=Guest.AgeCategory.ADULT,
            gender=Guest.Gender.MALE,
        )
        GuestEventInvitation.objects.create(
            guest=self.primary,
            event=self.event,
            attendance_status=Guest.RSVPStatus.ATTENDING,
        )
        GuestEventInvitation.objects.create(guest=self.companion, event=self.event)

    def test_companion_can_use_custom_event_availability(self):
        update_companion_attendance(
            primary_guest=self.primary,
            companion=self.companion,
            attendance_mode=Guest.AttendanceMode.CUSTOM,
            event_responses={WeddingEvent.Code.RECEPTION: Guest.RSVPStatus.NOT_ATTENDING},
        )

        self.companion.refresh_from_db()
        self.assertEqual(self.companion.attendance_mode, Guest.AttendanceMode.CUSTOM)
        self.assertEqual(
            self.companion.event_invitations.get(event=self.event).attendance_status,
            Guest.RSVPStatus.NOT_ATTENDING,
        )

    def test_positive_change_is_rejected_when_event_is_full(self):
        self.event.capacity = 1
        self.event.save(update_fields=["capacity"])
        with self.assertRaises(ValidationError):
            update_companion_attendance(
                primary_guest=self.primary,
                companion=self.companion,
                attendance_mode=Guest.AttendanceMode.CUSTOM,
                event_responses={WeddingEvent.Code.RECEPTION: Guest.RSVPStatus.ATTENDING},
            )

    def test_capacity_and_demographics_use_individual_attendance(self):
        snapshot = event_capacity_snapshot(self.event)
        statistics = demographic_statistics(self.event)

        self.assertEqual(snapshot["attending"], 1)
        self.assertTrue(any(row["total"] == 1 for row in statistics))


@override_settings(SECURE_SSL_REDIRECT=False)
class CapacityAdminTests(TestCase):
    def test_staff_can_view_capacity_dashboard_and_reception_list(self):
        admin = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="secret",
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("admin:guests_guest_capacity_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disponibilité sûre")
        self.assertContains(response, "Liste")
