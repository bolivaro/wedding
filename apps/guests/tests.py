from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from .models import Guest, GuestEventInvitation, WeddingEvent
from .services.companions import add_companion, deactivate_companion, update_companion
from .services.notifications import send_rsvp_notification
from .services.rsvp import update_rsvp
from .services.event_eligibility import apply_city_hall_policy
from .forms import CompanionAttendanceForm


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
    def _primary_with_events(self, **overrides):
        values = {
            "first_name": "Marie",
            "invitation_kind": Guest.InvitationKind.COUPLE,
            "party_size_limit": 2,
            **overrides,
        }
        primary = Guest.objects.create(**values)
        for event in WeddingEvent.objects.all():
            GuestEventInvitation.objects.create(
                guest=primary,
                event=event,
                is_eligible=True,
            )
        return primary

    def test_family_companion_is_eligible_for_city_hall(self):
        primary = self._primary_with_events(guest_group=Guest.GuestGroup.BRIDE_FAMILY)

        companion = add_companion(
            primary_guest=primary,
            first_name="Jean",
            last_name="Dupont",
            gender=Guest.Gender.MALE,
            age_category=Guest.AgeCategory.ADULT,
        )

        invitation = companion.event_invitations.get(event__code=WeddingEvent.Code.CITY_HALL)
        self.assertTrue(invitation.is_eligible)
        self.assertEqual(invitation.eligibility_source, GuestEventInvitation.EligibilitySource.POLICY)

    def test_friend_companion_is_not_eligible_for_city_hall(self):
        primary = self._primary_with_events(guest_group=Guest.GuestGroup.GROOM_FRIENDS)

        companion = add_companion(
            primary_guest=primary,
            first_name="Jean",
            last_name="Dupont",
            gender=Guest.Gender.MALE,
            age_category=Guest.AgeCategory.ADULT,
        )

        invitation = companion.event_invitations.get(event__code=WeddingEvent.Code.CITY_HALL)
        self.assertFalse(invitation.is_eligible)
        self.assertEqual(invitation.attendance_status, Guest.RSVPStatus.NOT_ATTENDING)

    def test_honor_companion_is_not_eligible_for_city_hall(self):
        primary = self._primary_with_events(
            guest_group=Guest.GuestGroup.BRIDE_FAMILY,
            guest_type=Guest.GuestType.HONOR,
        )

        companion = add_companion(
            primary_guest=primary,
            first_name="Jean",
            last_name="Dupont",
            gender=Guest.Gender.MALE,
            age_category=Guest.AgeCategory.ADULT,
        )

        self.assertFalse(
            companion.event_invitations.get(event__code=WeddingEvent.Code.CITY_HALL).is_eligible
        )

    def test_city_hall_policy_prioritizes_family_but_not_honor_companion(self):
        primary = self._primary_with_events(
            guest_group=Guest.GuestGroup.GROOM_FAMILY,
            guest_type=Guest.GuestType.HONOR,
        )
        companion = Guest.objects.create(
            first_name="Jean",
            invitation_owner=primary,
            is_active=True,
        )

        apply_city_hall_policy(primary)

        self.assertTrue(
            primary.event_invitations.get(event__code=WeddingEvent.Code.CITY_HALL).is_eligible
        )
        companion_invitation = companion.event_invitations.get(
            event__code=WeddingEvent.Code.CITY_HALL
        )
        self.assertFalse(companion_invitation.is_eligible)
        self.assertEqual(
            companion_invitation.eligibility_source,
            GuestEventInvitation.EligibilitySource.POLICY,
        )

    def test_attendance_inheritance_label_does_not_imply_event_eligibility(self):
        primary = self._primary_with_events(guest_group=Guest.GuestGroup.GROOM_FRIENDS)
        companion = add_companion(
            primary_guest=primary,
            first_name="Jean",
            last_name="Dupont",
            gender=Guest.Gender.MALE,
            age_category=Guest.AgeCategory.ADULT,
        )

        form = CompanionAttendanceForm(companion=companion)

        labels = dict(form.fields["attendance_mode"].choices)
        self.assertIn("événements inclus dans mon invitation", labels[Guest.AttendanceMode.INHERIT])
        self.assertIn("n’ajoute aucun événement", form.fields["attendance_mode"].help_text)

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
            age_category=Guest.AgeCategory.ADULT,
        )

        self.assertEqual(companion.invitation_owner, primary)
        self.assertEqual(companion.age_category, Guest.AgeCategory.ADULT)
        with self.assertRaises(ValidationError):
            add_companion(
                primary_guest=primary,
                first_name="Anne",
                last_name="Dupont",
                gender=Guest.Gender.FEMALE,
                age_category=Guest.AgeCategory.ADULT,
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
            age_category=Guest.AgeCategory.ADULT,
        )

        deactivate_companion(primary_guest=primary, companion=companion)

        companion.refresh_from_db()
        self.assertFalse(companion.is_active)
        self.assertEqual(companion.rsvp_status, Guest.RSVPStatus.NOT_ATTENDING)

    def test_update_existing_companion_preserves_record_and_event_invitations(self):
        primary = Guest.objects.create(
            first_name="Marie",
            invitation_kind=Guest.InvitationKind.COUPLE,
            party_size_limit=2,
        )
        event = WeddingEvent.objects.get(code=WeddingEvent.Code.CHURCH)
        companion = Guest.objects.create(
            first_name="Jean",
            last_name="Dupont",
            gender=Guest.Gender.MALE,
            invitation_owner=primary,
            age_category="",
        )
        invitation = GuestEventInvitation.objects.create(guest=companion, event=event)

        updated = update_companion(
            primary_guest=primary,
            companion=companion,
            first_name="Jeanne",
            last_name="Dupont",
            gender=Guest.Gender.FEMALE,
            age_category=Guest.AgeCategory.SENIOR,
        )

        self.assertEqual(updated.pk, companion.pk)
        self.assertEqual(updated.first_name, "Jeanne")
        self.assertEqual(updated.age_category, Guest.AgeCategory.SENIOR)
        self.assertTrue(
            GuestEventInvitation.objects.filter(pk=invitation.pk, guest=updated).exists()
        )


class RSVPNotificationTests(TestCase):
    @override_settings(RSVP_NOTIFICATION_EMAILS=["couple@example.com"])
    @patch("guests.services.notifications.send_brevo_email")
    def test_notification_contains_response_and_age_categories(self, send_email):
        primary = Guest.objects.create(
            first_name="Marie",
            last_name="Dupont",
            age_category=Guest.AgeCategory.CONFIRMED_ADULT,
            rsvp_status=Guest.RSVPStatus.NOT_ATTENDING,
            decline_reason=Guest.DeclineReason.TRAVEL,
            decline_message="Le trajet est trop compliqué.",
        )
        Guest.objects.create(
            first_name="Léa",
            last_name="Dupont",
            age_category=Guest.AgeCategory.TEENAGER,
            invitation_owner=primary,
        )

        send_rsvp_notification(guest=primary)

        send_email.assert_called_once()
        kwargs = send_email.call_args.kwargs
        self.assertEqual(kwargs["to"], [{"email": "couple@example.com"}])
        self.assertIn("Absence confirmée", kwargs["subject"])
        self.assertIn("Adulte confirmé (45–59)", kwargs["text_content"])
        self.assertIn("Adolescent (13–17)", kwargs["text_content"])
        self.assertIn("Distance ou déplacement", kwargs["text_content"])
        self.assertIn("Le trajet est trop compliqué.", kwargs["text_content"])


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
            decline_reason=Guest.DeclineReason.UNAVAILABLE,
            decline_message="Nous penserons très fort à vous.",
        )

        self.assertFalse(
            self.guest.event_invitations.exclude(
                attendance_status=Guest.RSVPStatus.NOT_ATTENDING
            ).exists()
        )
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.decline_reason, Guest.DeclineReason.UNAVAILABLE)
        self.assertEqual(self.guest.decline_message, "Nous penserons très fort à vous.")

# Create your tests here.
