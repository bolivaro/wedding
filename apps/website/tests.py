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

    def test_public_page_content_is_translated_to_english(self):
        expected_content = {
            "home": ("Your wedding space", "Explore the colours", "Plan my stay"),
            "program": ("The events of our day in order", "Plan your visit"),
            "dress_code": ("For this special day", "Burnt earth", "Let your elegance shine"),
            "stay": ("Stay & travel", "Your starting point", "Recommended areas"),
            "my_invitation": ("Your invitation is private", "Recover my access"),
        }

        for name, translated_strings in expected_content.items():
            with self.subTest(name=name):
                response = self.client.get(
                    reverse(f"website:{name}"), HTTP_ACCEPT_LANGUAGE="en"
                )
                self.assertEqual(response.headers["Content-Language"], "en")
                for translated_string in translated_strings:
                    self.assertContains(response, translated_string)

    def test_home_carousel_uses_proposal_photos_in_requested_order(self):
        response = self.client.get(reverse("website:home"))
        content = response.content.decode()
        images = (
            "website/images/carousel/proposal-hand.webp",
            "website/images/carousel/proposal-bir.webp",
            "website/images/carousel/couple-goal.webp",
        )

        for image in images:
            self.assertContains(response, image)
        self.assertLess(content.index(images[0]), content.index(images[1]))
        self.assertLess(content.index(images[1]), content.index(images[2]))
        self.assertContains(response, 'fetchpriority="high"', count=1)

    def test_program_only_displays_active_events_and_details(self):
        response = self.client.get(reverse("website:program"))
        self.assertContains(response, "Cérémonie civile")
        self.assertContains(response, "Retrouvons-nous à la mairie.")
        self.assertContains(response, "guests/images/program-icons/city-hall.svg")
        self.assertNotContains(response, "guests/images/program-icons/city_hall.svg")

    def test_program_explains_city_hall_capacity_limit(self):
        response = self.client.get(reverse("website:program"))

        self.assertContains(
            response,
            "En raison de la capacité limitée de la salle, la cérémonie civile se déroulera dans la stricte intimité familiale. Merci de vous référer à votre invitation.",
        )
        self.assertNotContains(response, "Masqué")

    def test_program_explains_arrangements_for_children_under_five(self):
        reception = WeddingEvent.objects.get(code=WeddingEvent.Code.RECEPTION)
        reception.is_active = True
        reception.save(update_fields=["is_active"])

        response = self.client.get(reverse("website:program"))

        self.assertContains(response, "À propos des jeunes enfants")
        self.assertContains(response, "enfants de moins de 5 ans")
        self.assertContains(response, "service de garde adapté sur place")

    def test_dress_code_contains_four_palettes(self):
        response = self.client.get(reverse("website:dress_code"))
        for name in ("Terre brûlée", "Verdoyant", "Sable doré", "Gris élégant"):
            self.assertContains(response, name)

        for label, color in (
            ("Brique", "#C04657"),
            ("Brun clair", "#C8A27A"),
            ("Olive", "#6F7050"),
            ("Vert nature", "#3F5545"),
            ("Beige sable", "#D6C3A5"),
            ("Moutarde", "#C89A2B"),
        ):
            self.assertContains(response, label)
            self.assertContains(response, color)

        for removed_color in ("Terracotta", "Cuivre", "Rouille", "Vert sauvage", "Champagne"):
            self.assertNotContains(response, removed_color)

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
        self.assertNotContains(response, "Notre sélection vérifiée sera publiée prochainement.")

    def test_public_footer_has_compact_ampersands(self):
        response = self.client.get(reverse("website:home"))

        self.assertContains(response, "L<i>&amp;</i>B")
        self.assertContains(response, "Leslie&amp;Bolivar")
        self.assertContains(response, "Version 1.2.0")

    def test_lodging_address_is_hidden_until_selected(self):
        response = self.client.get(reverse("website:stay"))
        self.assertContains(response, 'class="address-field" data-address-field hidden')
        self.assertContains(response, 'name="origin-kind" value="position" checked')

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
