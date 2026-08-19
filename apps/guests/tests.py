from datetime import datetime, timezone as datetime_timezone

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from .models import Guest, GuestEventInvitation, WeddingEvent
from .services.companions import add_companion, deactivate_companion
from .services.rsvp import update_rsvp


class GuestWorkflowFieldsTests(TestCase):
    def test_guest_can_be_created_without_email(self):
        first = Guest.objects.create(first_name="Marie")
        second = Guest.objects.create(first_name="Jean")

        self.assertIsNone(first.email)
        self.assertIsNone(second.email)

    def test_database_rejects_email_that_only_differs_by_case(self):
        Guest.objects.create(first_name="Marie", email="marie@example.com")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Guest.objects.create(first_name="Jean", email="MARIE@example.com")

    def test_salutation_is_derived_from_structured_gender(self):
        guest = Guest(first_name="Marie", gender=Guest.Gender.FEMALE)

        self.assertEqual(guest.salutation, "Mme")

    def test_family_invitation_requires_at_least_two_places(self):
        guest = Guest(
            first_name="Marie",
            invitation_kind=Guest.InvitationKind.FAMILY,
            party_size_limit=1,
        )

        with self.assertRaises(ValidationError):
            guest.full_clean()

    def test_database_rejects_invalid_couple_size(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Guest.objects.create(
                first_name="Marie",
                invitation_kind=Guest.InvitationKind.COUPLE,
                party_size_limit=3,
            )

    def test_companion_limit_excludes_primary_guest(self):
        guest = Guest(
            first_name="Marie",
            invitation_kind=Guest.InvitationKind.FAMILY,
            party_size_limit=5,
        )

        self.assertEqual(guest.companion_limit, 4)


class CompanionServiceTests(TestCase):
    def test_add_companion_respects_server_side_limit(self):
        primary = Guest.objects.create(
            first_name="Marie",
            invitation_kind=Guest.InvitationKind.COUPLE,
            party_size_limit=2,
        )

        companion = add_companion(
            primary_guest=primary,
            first_name="Jean",
            last_name="Dupont",
            gender=Guest.Gender.MALE,
        )

        self.assertEqual(companion.invitation_owner, primary)
        with self.assertRaises(ValidationError):
            add_companion(
                primary_guest=primary,
                first_name="Anne",
                last_name="Dupont",
                gender=Guest.Gender.FEMALE,
            )

    def test_remove_companion_preserves_guest_record(self):
        primary = Guest.objects.create(
            first_name="Marie",
            invitation_kind=Guest.InvitationKind.COUPLE,
            party_size_limit=2,
        )
        companion = add_companion(
            primary_guest=primary,
            first_name="Jean",
            last_name="Dupont",
            gender=Guest.Gender.MALE,
        )

        deactivate_companion(primary_guest=primary, companion=companion)

        companion.refresh_from_db()
        self.assertFalse(companion.is_active)
        self.assertEqual(companion.rsvp_status, Guest.RSVPStatus.NOT_ATTENDING)


class RSVPServiceTests(TestCase):
    def setUp(self):
        self.guest = Guest.objects.create(first_name="Marie")
        self.city_hall = WeddingEvent.objects.get(code=WeddingEvent.Code.CITY_HALL)
        self.church = WeddingEvent.objects.get(code=WeddingEvent.Code.CHURCH)
        GuestEventInvitation.objects.create(
            guest=self.guest,
            event=self.city_hall,
            is_eligible=False,
        )
        GuestEventInvitation.objects.create(
            guest=self.guest,
            event=self.church,
            is_eligible=True,
        )

    @override_settings(RSVP_DEADLINE=datetime(2099, 9, 15, tzinfo=datetime_timezone.utc))
    def test_ineligible_city_hall_cannot_be_accepted(self):
        with self.assertRaises(ValidationError):
            update_rsvp(
                guest=self.guest,
                status=Guest.RSVPStatus.ATTENDING,
                event_responses={
                    WeddingEvent.Code.CITY_HALL: Guest.RSVPStatus.ATTENDING,
                    WeddingEvent.Code.CHURCH: Guest.RSVPStatus.ATTENDING,
                },
            )

    @override_settings(RSVP_DEADLINE=datetime(2020, 9, 15, tzinfo=datetime_timezone.utc))
    def test_guest_cannot_modify_rsvp_after_deadline(self):
        with self.assertRaises(ValidationError):
            update_rsvp(
                guest=self.guest,
                status=Guest.RSVPStatus.NOT_ATTENDING,
            )

    @override_settings(RSVP_DEADLINE=datetime(2099, 9, 15, tzinfo=datetime_timezone.utc))
    def test_absence_sets_all_event_responses_to_absent(self):
        update_rsvp(
            guest=self.guest,
            status=Guest.RSVPStatus.NOT_ATTENDING,
        )

        self.assertFalse(
            self.guest.event_invitations.exclude(
                attendance_status=Guest.RSVPStatus.NOT_ATTENDING
            ).exists()
        )

# Create your tests here.
