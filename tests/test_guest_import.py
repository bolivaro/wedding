from io import BytesIO

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from guests.models import Guest, GuestImportBatch, GuestImportRow, WeddingEvent
from guests.services.import_guests import analyze_batch, apply_batch, upload_checksum
from specialdemands.models import SpecialDemand


IN_MEMORY_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def excel_row(**overrides):
    row = {
        "Nom": "DUPONT",
        "Prénom": "Marie",
        "Email": None,
        "Billet (S/C)": "C",
        "Places": 2,
        "Présence (P/A)": "P",
        "contact": "oui",
        "visa": "non",
        "Catégorie d’âge": "Adulte (18–44)",
        "Origine": "Cameroun",
        "Provenance": "France",
        "Mairie": "non",
        "Genre": "F",
    }
    row.update(overrides)
    return row


def build_workbook(rows_by_sheet=None):
    rows_by_sheet = rows_by_sheet or {"Famille femme": [excel_row()]}
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet in ["Famille femme", "Famille mari", "Amis femme", "Amis mari"]:
            pd.DataFrame(rows_by_sheet.get(sheet, []), columns=excel_row().keys()).to_excel(
                writer,
                sheet_name=sheet,
                index=False,
            )
        pd.DataFrame([{"Catégorie": "Totaux généraux"}]).to_excel(
            writer,
            sheet_name="Statistiques",
            index=False,
        )
    return output.getvalue()


@override_settings(STORAGES=IN_MEMORY_STORAGES)
class GuestImportServiceTests(TestCase):
    def create_batch(self, content=None):
        uploaded = SimpleUploadedFile(
            "invites.xlsx",
            content or build_workbook(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        return GuestImportBatch.objects.create(
            file=uploaded,
            original_filename=uploaded.name,
            checksum=upload_checksum(uploaded),
        )

    def test_new_guest_is_previewed_then_imported(self):
        batch = analyze_batch(self.create_batch())
        self.assertEqual(batch.summary, {GuestImportRow.Outcome.NEW: 1})
        self.assertEqual(Guest.objects.count(), 0)

        apply_batch(batch)

        guest = Guest.objects.get()
        self.assertEqual(batch.rows.get().outcome, GuestImportRow.Outcome.NEW)
        self.assertEqual(batch.rows.get().matched_guest, guest)
        self.assertEqual(guest.invitation_kind, Guest.InvitationKind.COUPLE)
        self.assertEqual(guest.rsvp_status, Guest.RSVPStatus.ATTENDING)
        self.assertEqual(guest.age_category, Guest.AgeCategory.ADULT)
        self.assertIsNone(guest.email)
        city_hall = guest.event_invitations.get(event__code=WeddingEvent.Code.CITY_HALL)
        self.assertFalse(city_hall.is_eligible)
        self.assertEqual(city_hall.attendance_status, Guest.RSVPStatus.PENDING)

    def test_existing_witness_is_merged_without_losing_role_or_relation(self):
        guest = Guest.objects.create(
            first_name="marie",
            last_name="dupont",
            email="marie@example.com",
            guest_type=Guest.GuestType.WITNESS,
            is_vip=True,
        )
        demand = SpecialDemand.objects.create(
            guest=guest,
            demand_type="witness",
            status="accepted",
        )

        batch = analyze_batch(self.create_batch())
        apply_batch(batch)

        guest.refresh_from_db()
        self.assertEqual(Guest.objects.count(), 1)
        self.assertEqual(guest.guest_type, Guest.GuestType.WITNESS)
        self.assertEqual(guest.email, "marie@example.com")
        self.assertTrue(SpecialDemand.objects.filter(pk=demand.pk, guest=guest).exists())

    def test_guest_response_has_priority_over_excel_presence(self):
        guest = Guest.objects.create(
            first_name="Marie",
            last_name="Dupont",
            rsvp_status=Guest.RSVPStatus.NOT_ATTENDING,
            rsvp_source=Guest.RSVPSource.GUEST,
        )

        batch = analyze_batch(self.create_batch())
        apply_batch(batch)

        guest.refresh_from_db()
        self.assertEqual(guest.rsvp_status, Guest.RSVPStatus.NOT_ATTENDING)
        self.assertEqual(guest.rsvp_source, Guest.RSVPSource.GUEST)

    def test_applying_same_batch_twice_is_idempotent(self):
        batch = analyze_batch(self.create_batch())
        apply_batch(batch)
        apply_batch(batch)
        self.assertEqual(Guest.objects.count(), 1)

    def test_ambiguous_name_is_not_merged(self):
        Guest.objects.create(first_name="Élodie", last_name="D'Arc")
        Guest.objects.create(first_name="Elodie", last_name="D Arc")
        content = build_workbook(
            {"Famille femme": [excel_row(**{"Prénom": "ELODIE", "Nom": "D-ARC"})]}
        )

        batch = analyze_batch(self.create_batch(content))

        self.assertEqual(batch.summary, {GuestImportRow.Outcome.CONFLICT: 1})

    def test_invalid_file_is_reported_without_guest_write(self):
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame([{"Nom": "DUPONT"}]).to_excel(
                writer,
                sheet_name="Famille femme",
                index=False,
            )

        batch = analyze_batch(self.create_batch(output.getvalue()))

        self.assertEqual(batch.status, GuestImportBatch.Status.FAILED)
        self.assertEqual(Guest.objects.count(), 0)

    def test_transaction_rolls_back_all_rows_on_apply_error(self):
        content = build_workbook(
            {"Famille femme": [excel_row(), excel_row(**{"Prénom": "Jean", "Genre": "H"})]}
        )
        batch = analyze_batch(self.create_batch(content))
        invalid_row = batch.rows.order_by("row_number").last()
        changes = invalid_row.proposed_changes
        changes["invitation_kind"] = {"old": None, "new": Guest.InvitationKind.COUPLE}
        changes["party_size_limit"] = {"old": None, "new": 3}
        invalid_row.proposed_changes = changes
        invalid_row.save(update_fields=["proposed_changes"])

        with self.assertRaises(ValidationError):
            apply_batch(batch)

        self.assertEqual(Guest.objects.count(), 0)


@override_settings(STORAGES=IN_MEMORY_STORAGES, SECURE_SSL_REDIRECT=False)
class GuestImportAdminTests(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="safe-test-password",
        )
        self.client.force_login(self.admin_user)

    def test_admin_can_preview_and_confirm_import(self):
        uploaded = SimpleUploadedFile(
            "invites.xlsx",
            build_workbook(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(reverse("admin:guests_guest_import"), {"file": uploaded})
        self.assertEqual(response.status_code, 302, response.content.decode())

        batch = GuestImportBatch.objects.get()
        preview_url = reverse(
            "admin:guests_guest_import_preview",
            kwargs={"batch_id": batch.pk},
        )
        self.assertRedirects(response, preview_url)
        self.assertEqual(batch.status, GuestImportBatch.Status.ANALYZED)

        response = self.client.post(
            reverse("admin:guests_guest_import_confirm", kwargs={"batch_id": batch.pk})
        )

        self.assertRedirects(response, preview_url)
        self.assertEqual(Guest.objects.count(), 1)
