from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from guests.models import Guest, GuestAccessCredential, GuestEventInvitation, WeddingEvent
from guests.services.access import CREDENTIAL_SESSION_KEY, GUEST_SESSION_KEY

from .models import Accommodation, StayArea
from .services.gifts import mask_iban, normalize_iban, normalize_paypal_url
from .services.thanks_video import extract_youtube_video_id, youtube_video_context


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
        for name in ("home", "program", "dress_code", "stay", "thanks", "my_invitation"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"website:{name}"))
                self.assertEqual(response.status_code, 200)

    def test_public_page_content_is_translated_to_english(self):
        expected_content = {
            "home": ("Your wedding space", "Explore the colours", "Plan my stay"),
            "program": ("The events of our day in order", "Plan your visit"),
            "dress_code": ("For this special day", "Burnt earth", "Let your elegance shine"),
            "stay": ("Stay & travel", "Your starting point", "Recommended areas"),
            "thanks": ("Thank you for writing this story with us", "Relive a few moments with us", "Share on WhatsApp"),
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
        self.assertContains(response, "Version 1.4.0")

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

    @override_settings(
        THANKS_YOUTUBE_URL="https://youtu.be/LiPlfsgWX04",
        SITE_BASE_URL="https://www.leslieniboli.fr",
    )
    def test_thanks_page_embeds_video_and_social_preview(self):
        response = self.client.get(reverse("website:thanks"))

        self.assertContains(response, "Merci d’avoir écrit cette histoire avec nous")
        self.assertContains(
            response,
            "https://www.youtube-nocookie.com/embed/LiPlfsgWX04?playsinline=1&amp;rel=0",
        )
        self.assertContains(response, 'referrerpolicy="strict-origin-when-cross-origin"')
        self.assertContains(response, 'content="noindex, nofollow"')
        self.assertContains(response, 'property="og:title"')
        self.assertContains(
            response,
            'content="https://i.ytimg.com/vi/LiPlfsgWX04/maxresdefault.jpg"',
        )
        self.assertContains(response, "https://www.leslieniboli.fr/merci/")
        self.assertContains(response, reverse("website:gifts"))

    @override_settings(
        THANKS_YOUTUBE_URL="https://youtu.be/LiPlfsgWX04",
        SITE_BASE_URL="https://www.leslieniboli.fr",
    )
    def test_thanks_whatsapp_message_contains_site_video_and_gift_links(self):
        response = self.client.get(reverse("website:thanks"))
        share_url = response.context["whatsapp_share_url"]
        message = parse_qs(urlparse(share_url).query)["text"][0]

        self.assertIn("https://www.leslieniboli.fr/merci/", message)
        self.assertIn("https://www.leslieniboli.fr/", message)
        self.assertIn("https://www.leslieniboli.fr/cadeaux/", message)

    @override_settings(THANKS_YOUTUBE_URL="https://example.com/not-youtube")
    def test_thanks_page_fails_safely_for_invalid_video_url(self):
        response = self.client.get(reverse("website:thanks"))

        self.assertContains(response, "La vidéo arrive bientôt")
        self.assertNotContains(response, "<iframe")

    def test_gifts_is_accessible_without_private_guest_access(self):
        response = self.client.get(reverse("website:gifts"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="robots" content="noindex, nofollow"')
        self.assertContains(response, "Votre présence, avant tout")

    @override_settings(
        GIFT_PAYPAL_LABEL="Leslie",
        GIFT_PAYPAL_URL="https://paypal.me/Leslie",
        GIFT_BANK_LABEL="Bolivar",
        GIFT_BANK_PROVIDER="Revolut",
        GIFT_BANK_ACCOUNT_HOLDER="Bolivar Exemple",
        GIFT_BANK_IBAN="FR76 3000 6000 0112 3456 7890 189",
        GIFT_BANK_BIC="AGRIFRPP",
    )
    def test_gifts_shows_paypal_and_revolut_bank_details_publicly(self):
        response = self.client.get(reverse("website:gifts"))

        self.assertContains(response, "Votre présence, avant tout")
        self.assertContains(response, "aucune participation attendue")
        self.assertContains(response, "https://paypal.me/Leslie")
        self.assertContains(response, "<h3>Leslie</h3>", html=True)
        self.assertContains(response, "<h3>Bolivar</h3>", html=True)
        self.assertContains(response, "Virement Revolut")
        self.assertContains(response, "Bolivar Exemple")
        self.assertContains(response, "FR76 •••• •••• •••• •••• •••• 189")
        self.assertNotContains(response, ">FR76 3000 6000 0112 3456 7890 189<")
        self.assertContains(response, "FR7630006000011234567890189")
        self.assertContains(response, "AGRIFRPP")
        self.assertContains(response, "Votre invitation et votre place ne dépendent évidemment d'aucune contribution.")

    @override_settings(
        GIFT_PAYPAL_LABEL="Leslie",
        GIFT_PAYPAL_URL="https://example.com/not-paypal",
        GIFT_BANK_LABEL="Bolivar",
        GIFT_BANK_PROVIDER="Revolut",
        GIFT_BANK_ACCOUNT_HOLDER="Bolivar Exemple",
        GIFT_BANK_IBAN="FR00 INVALID",
        GIFT_BANK_BIC="INVALID!",
    )
    def test_gifts_hides_invalid_payment_configuration(self):
        response = self.client.get(reverse("website:gifts"))

        self.assertContains(response, "La valise est encore fermée")
        self.assertNotContains(response, "example.com/not-paypal")
        self.assertNotContains(response, "FR00 INVALID")

    @override_settings(
        GIFT_PAYPAL_LABEL="Leslie",
        GIFT_PAYPAL_URL="",
        GIFT_BANK_LABEL="Bolivar",
        GIFT_BANK_PROVIDER="Revolut",
        GIFT_BANK_ACCOUNT_HOLDER="",
        GIFT_BANK_IBAN="",
        GIFT_BANK_BIC="",
    )
    def test_gifts_copy_is_translated_to_english(self):
        response = self.client.get(
            reverse("website:gifts"),
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertContains(response, "Your presence comes first")
        self.assertContains(response, "there is no pressure")


class GiftConfigurationTests(TestCase):
    def test_iban_is_masked_except_for_country_checksum_and_last_digits(self):
        self.assertEqual(
            mask_iban("FR76 3000 6000 0112 3456 7890 189"),
            "FR76 •••• •••• •••• •••• •••• 189",
        )

    def test_iban_checksum_is_validated_and_formatted(self):
        self.assertEqual(
            normalize_iban("fr76 3000 6000 0112 3456 7890 189"),
            "FR76 3000 6000 0112 3456 7890 189",
        )
        self.assertEqual(normalize_iban("FR00 3000 6000 0112 3456 7890 189"), "")

    def test_paypal_url_only_accepts_official_https_host(self):
        self.assertEqual(
            normalize_paypal_url("https://paypal.me/LeslieEtBolivar"),
            "https://paypal.me/LeslieEtBolivar",
        )
        for unsafe_url in (
            "http://paypal.me/LeslieEtBolivar",
            "https://paypal.me.example.test/LeslieEtBolivar",
            "https://example.test/?next=paypal.me",
            "https://paypal.me",
        ):
            with self.subTest(url=unsafe_url):
                self.assertEqual(normalize_paypal_url(unsafe_url), "")


class ThanksVideoConfigurationTests(TestCase):
    def test_supported_youtube_urls_are_normalized(self):
        for url in (
            "https://youtu.be/LiPlfsgWX04",
            "https://www.youtube.com/watch?v=LiPlfsgWX04",
            "https://youtube.com/embed/LiPlfsgWX04",
        ):
            with self.subTest(url=url):
                self.assertEqual(extract_youtube_video_id(url), "LiPlfsgWX04")

    def test_untrusted_or_invalid_video_urls_are_rejected(self):
        for url in (
            "http://youtu.be/LiPlfsgWX04",
            "https://youtube.example/LiPlfsgWX04",
            "https://youtu.be/not-valid",
            "javascript:alert(1)",
        ):
            with self.subTest(url=url):
                self.assertEqual(extract_youtube_video_id(url), "")

    def test_video_context_uses_privacy_enhanced_embed(self):
        context = youtube_video_context("https://youtu.be/LiPlfsgWX04")

        self.assertEqual(context["watch_url"], "https://youtu.be/LiPlfsgWX04")
        self.assertEqual(
            context["embed_url"],
            "https://www.youtube-nocookie.com/embed/LiPlfsgWX04?playsinline=1&rel=0",
        )
        self.assertEqual(
            context["thumbnail_url"],
            "https://i.ytimg.com/vi/LiPlfsgWX04/maxresdefault.jpg",
        )
