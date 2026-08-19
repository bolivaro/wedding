from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Guest


class GuestWorkflowFieldsTests(TestCase):
    def test_guest_can_be_created_without_email(self):
        first = Guest.objects.create(first_name="Marie")
        second = Guest.objects.create(first_name="Jean")

        self.assertIsNone(first.email)
        self.assertIsNone(second.email)

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

# Create your tests here.
