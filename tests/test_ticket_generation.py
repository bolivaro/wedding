import base64
import hashlib
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops, ImageColor
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone as django_timezone

from guests.models import Guest, GuestEventInvitation, Ticket, WeddingEvent
from guests.services.access import issue_guest_access
from guests.services.notifications import send_ticket_email
from guests.services.ticket import (
    DRESS_CODE_PALETTES,
    PROGRAM_ICON_ASSETS,
    _make_qr_image,
    _paste_event_icon,
    build_information_jpg,
    build_party_pdf,
    generate_ticket,
    qr_payload,
    ticket_is_current,
)


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
OPEN_DEADLINE = datetime(2099, 9, 15, 23, 59, tzinfo=timezone.utc)


@override_settings(
    RSVP_DEADLINE=OPEN_DEADLINE,
    SECURE_SSL_REDIRECT=False,
    SITE_BASE_URL="https://example.test",
    WEDDING_PROGRAM_URL="https://example.test/programme/",
    WEDDING_DRESS_CODE_URL="https://example.test/dress-code/",
    STORAGES=TEST_STORAGES,
)
class TicketGenerationTests(TestCase):
    def setUp(self):
        self.primary = Guest.objects.create(
            first_name="Élodie",
            last_name="Du Pré",
            gender=Guest.Gender.FEMALE,
            invitation_kind=Guest.InvitationKind.COUPLE,
            party_size_limit=2,
            rsvp_status=Guest.RSVPStatus.ATTENDING,
        )
        self.companion = Guest.objects.create(
            first_name="Jean",
            last_name="Du Pré",
            gender=Guest.Gender.MALE,
            invitation_owner=self.primary,
        )
        for event in WeddingEvent.objects.all():
            GuestEventInvitation.objects.create(
                guest=self.primary,
                event=event,
                is_eligible=True,
                attendance_status=Guest.RSVPStatus.ATTENDING,
            )

    def _template_bytes(self):
        template = Path(__file__).parents[1] / (
            "apps/guests/static/guests/images/billet-template-v1.jpg"
        )
        return template.read_bytes()

    def test_generation_creates_real_jpg_and_pdf_without_touching_template(self):
        template_before = hashlib.sha256(self._template_bytes()).hexdigest()

        ticket = generate_ticket(self.primary)

        self.assertTrue(ticket.is_ready)
        ticket.jpg_file.open("rb")
        jpg_content = ticket.jpg_file.read()
        ticket.jpg_file.close()
        with Image.open(io.BytesIO(jpg_content)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (1796, 2528))
        self.assertEqual(ticket.template_version, "billet-v1")
        ticket.pdf_file.open("rb")
        pdf_content = ticket.pdf_file.read()
        ticket.pdf_file.close()
        self.assertTrue(pdf_content.startswith(b"%PDF"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page(?!s)", pdf_content)), 2)
        self.assertIn(b"https://example.test/programme/", pdf_content)
        self.assertIn(b"https://example.test/dress-code/", pdf_content)
        self.assertIn(b"https://www.google.com/maps/", pdf_content)
        self.assertEqual(template_before, hashlib.sha256(self._template_bytes()).hexdigest())

    def test_five_names_fit_on_the_real_template(self):
        self.primary.invitation_kind = Guest.InvitationKind.FAMILY
        self.primary.party_size_limit = 5
        self.primary.save(update_fields=["invitation_kind", "party_size_limit", "updated_at"])
        for first_name in ("Anaïs", "Alexandre", "Joséphine"):
            Guest.objects.create(
                first_name=first_name,
                last_name="De La Tour-Dupont",
                invitation_owner=self.primary,
            )

        ticket = generate_ticket(self.primary, force=True)

        ticket.jpg_file.open("rb")
        with Image.open(ticket.jpg_file) as image:
            names_area = image.crop((100, 100, 1696, 480)).convert("RGB")
            self.assertGreater(len(names_area.getcolors(maxcolors=1_000_000)), 1)
        ticket.jpg_file.close()

    def test_qr_uses_exact_terracotta_modules_without_interpolation(self):
        qr_image = _make_qr_image(qr_payload(self.primary), max_size=240)

        self.assertLessEqual(qr_image.width, 240)
        self.assertEqual(qr_image.width, qr_image.height)
        self.assertEqual(
            set(qr_image.getdata()),
            {(177, 34, 0), (255, 238, 236)},
        )

    def test_program_change_invalidates_existing_ticket(self):
        ticket = generate_ticket(self.primary)
        event = WeddingEvent.objects.get(code=WeddingEvent.Code.RECEPTION)
        event.icon = WeddingEvent.EventIcon.PARTY
        event.save(update_fields=["icon"])

        self.assertFalse(ticket_is_current(ticket, self.primary))

    def test_program_icons_use_the_recolored_attached_vector_assets(self):
        expected_icons = {
            WeddingEvent.EventIcon.CITY_HALL,
            WeddingEvent.EventIcon.CHURCH,
            WeddingEvent.EventIcon.TOAST,
            WeddingEvent.EventIcon.DINNER,
        }
        self.assertEqual(set(PROGRAM_ICON_ASSETS), expected_icons)
        static_root = Path(__file__).parents[1] / "apps/guests/static"

        for icon, assets in PROGRAM_ICON_ASSETS.items():
            with self.subTest(icon=icon):
                source = static_root / assets["source"]
                raster = static_root / assets["raster"]
                source_content = source.read_text(encoding="utf-8")
                self.assertIn("#CD9241", source_content)
                self.assertNotIn("#000000", source_content)

                with Image.open(raster) as raster_image:
                    self.assertEqual(raster_image.size, (1024, 1024))
                    self.assertEqual(raster_image.mode, "RGBA")
                    self.assertIn(
                        (205, 146, 65),
                        {
                            pixel[:3]
                            for pixel in raster_image.getdata()
                            if pixel[3] == 255
                        },
                    )

                background = Image.new("RGB", (120, 120), "#FFEEEC")
                image = background.copy()
                rendered = _paste_event_icon(image, icon, (5, 5, 115, 115))

                self.assertTrue(rendered)
                self.assertIsNotNone(ImageChops.difference(image, background).getbbox())

    def test_party_icon_keeps_the_existing_fallback_without_an_asset(self):
        image = Image.new("RGB", (120, 120), "#FFEEEC")

        self.assertFalse(
            _paste_event_icon(
                image,
                WeddingEvent.EventIcon.PARTY,
                (5, 5, 115, 115),
            )
        )

    def test_information_jpg_uses_reference_dimensions(self):
        content = build_information_jpg()

        with Image.open(io.BytesIO(content)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (1796, 2528))

    def test_information_page_uses_current_dress_code_palette(self):
        self.assertEqual(
            DRESS_CODE_PALETTES,
            (
                ("Terre brûlée", (("Brique", "#C04657"), ("Brun clair", "#C8A27A"))),
                ("Vert nature", (("Olive", "#6F7050"), ("Vert nature", "#3F5545"))),
                ("Sable doré", (("Beige sable", "#D6C3A5"), ("Moutarde", "#C89A2B"))),
                ("Gris élégant", (("Perle", "#B8B3AA"), ("Anthracite", "#4B4B49"))),
            ),
        )

        with Image.open(io.BytesIO(build_information_jpg())) as image:
            for palette_index, (_, shades) in enumerate(DRESS_CODE_PALETTES):
                row, column = divmod(palette_index, 2)
                for shade_index, (_, color) in enumerate(shades):
                    actual = image.getpixel(
                        (335 + column * 680 + shade_index * 290, 1762 + row * 155)
                    )
                    expected = ImageColor.getrgb(color)
                    self.assertLessEqual(
                        max(abs(channel - target) for channel, target in zip(actual, expected)),
                        12,
                    )

    def test_qr_payload_is_opaque_and_stable_when_identity_changes(self):
        initial_payload = qr_payload(self.primary)
        initial_token = self.primary.qr_token
        ticket = generate_ticket(self.primary)
        initial_signature = ticket.render_signature

        self.primary.last_name = "Nouveau nom"
        self.primary.save(update_fields=["last_name", "updated_at"])
        ticket = generate_ticket(self.primary)

        self.assertEqual(qr_payload(self.primary), initial_payload)
        self.assertEqual(self.primary.qr_token, initial_token)
        self.assertNotIn("Nouveau", initial_payload)
        self.assertNotEqual(ticket.render_signature, initial_signature)

    def test_generation_is_idempotent_while_ticket_is_current(self):
        first = generate_ticket(self.primary)
        first_jpg_name = first.jpg_file.name
        generated_at = first.generated_at

        second = generate_ticket(self.primary)

        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.jpg_file.name, first_jpg_name)
        self.assertEqual(second.generated_at, generated_at)
        self.assertTrue(ticket_is_current(second, self.primary))

    def test_party_has_one_group_ticket_and_one_qr(self):
        content = build_party_pdf(self.primary)

        self.assertTrue(content.startswith(b"%PDF"))
        self.assertTrue(Ticket.objects.get(guest=self.primary).is_ready)
        self.assertFalse(Ticket.objects.filter(guest=self.companion).exists())
        self.assertEqual(qr_payload(self.primary), qr_payload(self.companion))

    def test_legacy_companion_ticket_is_preserved_but_not_regenerated(self):
        legacy_ticket = Ticket.objects.create(guest=self.companion)

        group_ticket = generate_ticket(self.companion)

        self.assertEqual(group_ticket.guest, self.primary)
        self.assertTrue(Ticket.objects.filter(pk=legacy_ticket.pk).exists())
        legacy_ticket.refresh_from_db()
        self.assertEqual(legacy_ticket.status, Ticket.Status.PENDING)

    def test_companion_change_makes_group_ticket_stale(self):
        ticket = generate_ticket(self.primary)
        self.assertTrue(ticket_is_current(ticket, self.primary))

        self.companion.first_name = "Nouveau prénom"
        self.companion.save(update_fields=["first_name", "updated_at"])

        self.assertFalse(ticket_is_current(ticket, self.primary))

    @patch("guests.services.notifications.send_brevo_email")
    def test_ticket_email_builds_a_brevo_pdf_attachment(self, send_email):
        self.primary.email = "elodie@example.com"
        self.primary.email_verified_at = django_timezone.now()
        pdf_content = b"%PDF-test"

        send_ticket_email(guest=self.primary, pdf_content=pdf_content)

        attachment = send_email.call_args.kwargs["attachments"][0]
        self.assertEqual(attachment["name"], "billet-groupe-mariage.pdf")
        self.assertEqual(base64.b64decode(attachment["content"]), pdf_content)


@override_settings(
    RSVP_DEADLINE=OPEN_DEADLINE,
    SECURE_SSL_REDIRECT=False,
    SITE_BASE_URL="https://example.test",
    WEDDING_PROGRAM_URL="https://example.test/programme/",
    WEDDING_DRESS_CODE_URL="https://example.test/dress-code/",
    STORAGES=TEST_STORAGES,
)
class TicketViewsTests(TestCase):
    def setUp(self):
        self.primary = Guest.objects.create(
            first_name="Marie",
            last_name="Dupont",
            invitation_kind=Guest.InvitationKind.COUPLE,
            party_size_limit=2,
            rsvp_status=Guest.RSVPStatus.ATTENDING,
        )
        self.companion = Guest.objects.create(
            first_name="Jean",
            last_name="Dupont",
            invitation_owner=self.primary,
        )
        self.unrelated = Guest.objects.create(first_name="Intrus")
        for event in WeddingEvent.objects.all():
            GuestEventInvitation.objects.create(
                guest=self.primary,
                event=event,
                is_eligible=True,
                attendance_status=Guest.RSVPStatus.ATTENDING,
            )
        issued = issue_guest_access(guest=self.primary)
        self.client.get(
            reverse(
                "guests:access_entry",
                kwargs={"selector": issued.credential.selector, "secret": issued.secret},
            )
        )

    def test_companion_route_generates_and_downloads_the_group_ticket(self):
        response = self.client.post(
            reverse("guests:ticket_generate", kwargs={"guest_id": self.companion.pk})
        )
        self.assertRedirects(response, reverse("guests:ticket_preview"))
        self.assertTrue(Ticket.objects.filter(guest=self.primary).exists())
        self.assertFalse(Ticket.objects.filter(guest=self.companion).exists())

        response = self.client.get(
            reverse(
                "guests:ticket_download",
                kwargs={"guest_id": self.companion.pk, "file_format": "jpg"},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")

    def test_ticket_center_shows_one_group_card_and_all_members(self):
        response = self.client.get(reverse("guests:ticket_preview"))

        self.assertContains(response, "Marie Dupont")
        self.assertContains(response, "Jean Dupont")
        self.assertContains(
            response,
            'class="ticket-person-card ticket-group-card card"',
            count=1,
        )

    def test_information_jpg_can_be_downloaded_separately(self):
        response = self.client.get(reverse("guests:ticket_information_download"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertIn("programme-et-dress-code.jpg", response["Content-Disposition"])
        with Image.open(io.BytesIO(response.content)) as image:
            self.assertEqual(image.size, (1796, 2528))

    def test_primary_cannot_reach_unrelated_ticket(self):
        response = self.client.post(
            reverse("guests:ticket_generate", kwargs={"guest_id": self.unrelated.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Ticket.objects.filter(guest=self.unrelated).exists())

    @patch("guests.views.send_ticket_email")
    def test_email_delivery_requires_verified_address(self, send_email):
        response = self.client.post(reverse("guests:ticket_email"))
        self.assertRedirects(response, reverse("guests:ticket_preview"))
        send_email.assert_not_called()

        self.primary.email = "marie@example.com"
        self.primary.email_verified_at = django_timezone.now()
        self.primary.save(update_fields=["email", "email_verified_at", "updated_at"])
        response = self.client.post(reverse("guests:ticket_email"))

        self.assertRedirects(response, reverse("guests:ticket_preview"))
        send_email.assert_called_once()
        self.assertTrue(send_email.call_args.kwargs["pdf_content"].startswith(b"%PDF"))


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=TEST_STORAGES)
class TicketAdminTests(TestCase):
    def test_admin_can_generate_selected_ticket(self):
        admin = get_user_model().objects.create_superuser(
            username="ticket-admin",
            email="admin@example.com",
            password="safe-test-password",
        )
        guest = Guest.objects.create(first_name="Marie")
        self.client.force_login(admin)

        response = self.client.post(
            reverse("admin:guests_guest_changelist"),
            {
                "action": "generate_selected_tickets",
                "_selected_action": [guest.pk],
            },
            follow=True,
        )

        self.assertContains(response, "1 billet(s) de groupe prêt(s).")
        self.assertTrue(Ticket.objects.get(guest=guest).is_ready)

    def test_selecting_companion_generates_primary_group_ticket(self):
        admin = get_user_model().objects.create_superuser(
            username="companion-ticket-admin",
            email="companion-admin@example.com",
            password="safe-test-password",
        )
        primary = Guest.objects.create(first_name="Marie")
        companion = Guest.objects.create(first_name="Jean", invitation_owner=primary)
        self.client.force_login(admin)

        response = self.client.post(
            reverse("admin:guests_guest_changelist"),
            {
                "action": "generate_selected_tickets",
                "_selected_action": [companion.pk],
            },
            follow=True,
        )

        self.assertContains(response, "1 billet(s) de groupe prêt(s).")
        self.assertTrue(Ticket.objects.filter(guest=primary).exists())
        self.assertFalse(Ticket.objects.filter(guest=companion).exists())
