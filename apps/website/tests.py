from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from guests.models import Guest, GuestAccessCredential, GuestEventInvitation, WeddingEvent
from guests.services.access import CREDENTIAL_SESSION_KEY, GUEST_SESSION_KEY

from .models import Accommodation, StayArea


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class PublicWebsiteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = WeddingEvent.objects.get(code=WeddingEvent.Code.CITY_HALL)
        cls.event.name = "Cérémonie civile"
        cls.event.description = "Retrouvons-nous à la mairie."
        cls.event.starts_at = timezone.now()
        cls.event.is_active = True
        cls.event.save()
        hidden = WeddingEvent.objects.get(code=WeddingEvent.Code.CHURCH)
        hidden.name = "Masqué"
        hidden.is_active = False
        hidden.save()
        cls.area = StayArea.objects.create(
            name="Puteaux",
            slug="puteaux",
            summary="Près des cérémonies",
            is_published=True,
        )

    def test_public_pages_are_accessible(self):
        for name in ("home", "program", "dress_code", "stay", "my_invitation"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"website:{name}"))
                self.assertEqual(response.status_code, 200)

    def test_program_only_displays_active_events_and_details(self):
        response = self.client.get(reverse("website:program"))
        self.assertContains(response, "Cérémonie civile")
        self.assertContains(response, "Retrouvons-nous à la mairie.")
        self.assertNotContains(response, "Masqué")

    def test_dress_code_contains_four_palettes(self):
        response = self.client.get(reverse("website:dress_code"))
        for name in ("Terre brûlée", "Vert nature", "Sable doré", "Gris élégant"):
            self.assertContains(response, name)

    def test_unpublished_accommodation_is_not_displayed(self):
        Accommodation.objects.create(
            area=self.area,
            name="Brouillon secret",
            accommodation_type=Accommodation.Type.HOTEL,
            booking_url="https://example.test",
            is_published=False,
        )
        response = self.client.get(reverse("website:stay"))
        self.assertNotContains(response, "Brouillon secret")

    @override_settings(GUEST_ACCESS_LIFETIME_DAYS=120)
    def test_private_session_changes_invitation_link_and_prefills_events(self):
        guest = Guest.objects.create(first_name="Amina")
        invitation = GuestEventInvitation.objects.create(
            guest=guest,
            event=self.event,
            is_eligible=True,
            attendance_status=Guest.RSVPStatus.ATTENDING,
        )
        credential = GuestAccessCredential.objects.create(
            guest=guest,
            secret_hash="unused",
            expires_at=timezone.now() + timedelta(days=1),
        )
        session = self.client.session
        session[GUEST_SESSION_KEY] = guest.pk
        session[CREDENTIAL_SESSION_KEY] = credential.pk
        session.save()

        response = self.client.get(reverse("website:stay"))
        self.assertContains(response, "Mon RSVP")
        self.assertContains(response, f'value="{invitation.event.code}" data-event-choice checked')

    def test_my_invitation_redirects_authenticated_guest(self):
        guest = Guest.objects.create(first_name="Noah")
        credential = GuestAccessCredential.objects.create(
            guest=guest,
            secret_hash="unused",
            expires_at=timezone.now() + timedelta(days=1),
        )
        session = self.client.session
        session[GUEST_SESSION_KEY] = guest.pk
        session[CREDENTIAL_SESSION_KEY] = credential.pk
        session.save()
        response = self.client.get(reverse("website:my_invitation"))
        self.assertRedirects(response, reverse("guests:rsvp_dashboard"), fetch_redirect_response=False)
