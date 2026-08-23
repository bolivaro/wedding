import hashlib
import re
import unicodedata
from collections import Counter, defaultdict

import pandas as pd
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from guests.models import (
    Guest,
    GuestEventInvitation,
    GuestImportBatch,
    GuestImportRow,
    GuestSourceRecord,
    WeddingEvent,
)


INVITATION_SHEETS = {
    "Famille femme": Guest.GuestGroup.BRIDE_FAMILY,
    "Famille mari": Guest.GuestGroup.GROOM_FAMILY,
    "Amis femme": Guest.GuestGroup.BRIDE_FRIENDS,
    "Amis mari": Guest.GuestGroup.GROOM_FRIENDS,
}
REQUIRED_COLUMNS = {
    "Nom",
    "Prénom",
    "Email",
    "Billet (S/C)",
    "Places",
    "Présence (P/A)",
    "contact",
    "visa",
    "Catégorie d’âge",
    "Origine",
    "Provenance",
    "Mairie",
    "Genre",
}


def upload_checksum(uploaded_file):
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()


def normalize_identity(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.casefold().replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _clean_cell(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        return " ".join(value.split())
    if hasattr(value, "item"):
        return value.item()
    return value


def _normalized_email(value):
    return str(value or "").strip().casefold()


def _parse_age_category(value):
    normalized = normalize_identity(value)
    aliases = {
        normalize_identity("Bébé (0–2)"): Guest.AgeCategory.BABY,
        normalize_identity("Bébé (0–2 ans)"): Guest.AgeCategory.BABY,
        normalize_identity("Enfant (3–12)"): Guest.AgeCategory.CHILD,
        normalize_identity("Enfant (3–12 ans)"): Guest.AgeCategory.CHILD,
        normalize_identity("Adolescent (13–17)"): Guest.AgeCategory.TEENAGER,
        normalize_identity("Adolescent (13–17 ans)"): Guest.AgeCategory.TEENAGER,
        normalize_identity("Adulte (18–44)"): Guest.AgeCategory.ADULT,
        normalize_identity("Adulte (18–44 ans)"): Guest.AgeCategory.ADULT,
        normalize_identity("Adulte confirmé (45–59)"): Guest.AgeCategory.CONFIRMED_ADULT,
        normalize_identity("Adulte confirmé (45–59 ans)"): Guest.AgeCategory.CONFIRMED_ADULT,
        normalize_identity("Senior (60+)"): Guest.AgeCategory.SENIOR,
        normalize_identity("Senior (60 ans et plus)"): Guest.AgeCategory.SENIOR,
    }
    return aliases.get(normalized)


def _source_key(sheet_name, first_name, last_name):
    return f"{sheet_name}|{normalize_identity(first_name)}|{normalize_identity(last_name)}"


def _parse_row(sheet_name, row_number, raw):
    data = {column: _clean_cell(raw.get(column)) for column in REQUIRED_COLUMNS}
    messages = []
    first_name = str(data["Prénom"] or "").strip()
    last_name = str(data["Nom"] or "").strip()
    email = _normalized_email(data["Email"]) or None
    ticket = str(data["Billet (S/C)"] or "").upper()
    presence = str(data["Présence (P/A)"] or "").upper()
    city_hall = str(data["Mairie"] or "").casefold()
    gender = str(data["Genre"] or "").upper()
    age_category = _parse_age_category(data["Catégorie d’âge"])

    if not first_name or not last_name:
        messages.append("Le nom et le prénom sont obligatoires.")
    if email:
        try:
            validate_email(email)
        except ValidationError:
            messages.append("L'adresse email est invalide.")
    if ticket not in {"S", "C", "F"}:
        messages.append("La nature de l'invitation doit être S, C ou F.")

    expected_places = {"S": 1, "C": 2}.get(ticket)
    try:
        places = int(data["Places"])
    except (TypeError, ValueError):
        places = 0
    if expected_places and places != expected_places:
        messages.append(f"Une invitation {ticket} doit contenir {expected_places} place(s).")
    if ticket == "F" and places < 2:
        messages.append("Une invitation famille doit contenir au moins deux places.")
    if presence not in {"P", "A"}:
        messages.append("La présence doit être P ou A.")
    if city_hall not in {"oui", "non"}:
        messages.append("La valeur Mairie doit être oui ou non.")
    if gender not in {"H", "F"}:
        messages.append("Le genre doit être H ou F.")
    if age_category is None:
        messages.append("La catégorie d’âge ne correspond pas aux tranches autorisées.")

    yes_no = {}
    for column in ["contact", "visa"]:
        value = str(data[column] or "").casefold()
        if value not in {"oui", "non"}:
            messages.append(f"La valeur {column} doit être oui ou non.")
        yes_no[column] = value == "oui"

    parsed = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "guest_group": INVITATION_SHEETS[sheet_name],
        "invitation_kind": {
            "S": Guest.InvitationKind.SINGLE,
            "C": Guest.InvitationKind.COUPLE,
            "F": Guest.InvitationKind.FAMILY,
        }.get(ticket),
        "party_size_limit": places,
        "rsvp_status": {
            "P": Guest.RSVPStatus.ATTENDING,
            "A": Guest.RSVPStatus.NOT_ATTENDING,
        }.get(presence),
        "has_been_contacted": yes_no["contact"],
        "requires_visa": yes_no["visa"],
        "age_category": age_category,
        "origin_country": str(data["Origine"] or ""),
        "travel_origin_country": str(data["Provenance"] or ""),
        "gender": {
            "H": Guest.Gender.MALE,
            "F": Guest.Gender.FEMALE,
        }.get(gender),
        "city_hall_eligible": city_hall == "oui",
    }
    return data, parsed, messages


def _differences(guest, parsed):
    changes = {}
    managed_fields = [
        "first_name",
        "last_name",
        "guest_group",
        "invitation_kind",
        "party_size_limit",
        "has_been_contacted",
        "requires_visa",
        "age_category",
        "origin_country",
        "travel_origin_country",
        "gender",
    ]
    if parsed["email"]:
        managed_fields.append("email")
    if guest.rsvp_source not in {Guest.RSVPSource.GUEST, Guest.RSVPSource.ADMIN}:
        managed_fields.append("rsvp_status")

    for field in managed_fields:
        old_value = getattr(guest, field)
        new_value = parsed[field]
        if old_value != new_value:
            changes[field] = {"old": old_value, "new": new_value}

    city_hall = guest.event_invitations.filter(event__code=WeddingEvent.Code.CITY_HALL).first()
    old_eligibility = city_hall.is_eligible if city_hall else None
    if old_eligibility != parsed["city_hall_eligible"]:
        changes["city_hall_eligible"] = {
            "old": old_eligibility,
            "new": parsed["city_hall_eligible"],
        }
    return changes


@transaction.atomic
def analyze_batch(batch):
    batch.rows.all().delete()
    batch.error_message = ""

    try:
        batch.file.open("rb")
        workbook = pd.ExcelFile(batch.file, engine="openpyxl")
        missing_sheets = set(INVITATION_SHEETS) - set(workbook.sheet_names)
        if missing_sheets:
            raise ValidationError(
                "Feuilles manquantes : " + ", ".join(sorted(missing_sheets))
            )

        candidates = []
        for sheet_name in INVITATION_SHEETS:
            dataframe = pd.read_excel(workbook, sheet_name=sheet_name)
            missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)
            if missing_columns:
                raise ValidationError(
                    f"Colonnes manquantes dans {sheet_name} : "
                    + ", ".join(sorted(missing_columns))
                )
            for index, raw in dataframe.iterrows():
                if pd.isna(raw.get("Nom")) and pd.isna(raw.get("Prénom")):
                    continue
                data, parsed, messages = _parse_row(sheet_name, index + 2, raw)
                key = _source_key(sheet_name, parsed["first_name"], parsed["last_name"])
                candidates.append((sheet_name, index + 2, key, data, parsed, messages))

        key_counts = Counter(candidate[2] for candidate in candidates)
        guests = list(Guest.objects.prefetch_related("event_invitations__event"))
        names = defaultdict(list)
        emails = defaultdict(list)
        for guest in guests:
            names[(normalize_identity(guest.first_name), normalize_identity(guest.last_name))].append(guest)
            if guest.email:
                emails[_normalized_email(guest.email)].append(guest)
        source_records = {
            record.external_key: record.guest
            for record in GuestSourceRecord.objects.select_related("guest").filter(source="excel")
        }

        rows = []
        summary = Counter()
        for sheet_name, row_number, key, data, parsed, validation_messages in candidates:
            messages = list(validation_messages)
            matched_guest = None
            outcome = GuestImportRow.Outcome.NEW

            if messages:
                outcome = GuestImportRow.Outcome.INVALID
            elif key_counts[key] > 1:
                outcome = GuestImportRow.Outcome.AMBIGUOUS
                messages.append("Cette identité apparaît plusieurs fois dans le fichier.")
            else:
                source_match = source_records.get(key)
                name_matches = names[(normalize_identity(parsed["first_name"]), normalize_identity(parsed["last_name"]))]
                email_matches = emails.get(parsed["email"], []) if parsed["email"] else []
                possible = {guest.pk: guest for guest in [source_match, *name_matches, *email_matches] if guest}
                if len(possible) == 1:
                    matched_guest = next(iter(possible.values()))
                    outcome = GuestImportRow.Outcome.MATCHED
                elif len(possible) > 1:
                    outcome = GuestImportRow.Outcome.CONFLICT
                    messages.append("L'email, le nom ou l'identité source désignent plusieurs invités.")

            changes = _differences(matched_guest, parsed) if matched_guest else {
                field: {"old": None, "new": value}
                for field, value in parsed.items()
                if value is not None
            }
            if matched_guest and matched_guest.rsvp_source in {Guest.RSVPSource.GUEST, Guest.RSVPSource.ADMIN} and matched_guest.rsvp_status != parsed["rsvp_status"]:
                messages.append("La réponse RSVP existante est prioritaire sur la valeur Excel.")

            rows.append(
                GuestImportRow(
                    batch=batch,
                    sheet_name=sheet_name,
                    row_number=row_number,
                    source_key=key,
                    raw_data=data,
                    outcome=outcome,
                    matched_guest=matched_guest,
                    proposed_changes=changes,
                    messages=messages,
                )
            )
            summary[outcome] += 1

        GuestImportRow.objects.bulk_create(rows)
        batch.status = GuestImportBatch.Status.ANALYZED
        batch.summary = dict(summary)
        batch.save(update_fields=["status", "summary", "error_message"])
        return batch
    except Exception as exc:
        batch.status = GuestImportBatch.Status.FAILED
        batch.error_message = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        batch.save(update_fields=["status", "error_message"])
        return batch
    finally:
        batch.file.close()


def _apply_event_invitations(guest, parsed, response_time):
    events = {event.code: event for event in WeddingEvent.objects.filter(is_active=True)}
    for code, event in events.items():
        eligibility = parsed["city_hall_eligible"] if code == WeddingEvent.Code.CITY_HALL else True
        defaults = {
            "is_eligible": eligibility,
            "eligibility_source": GuestEventInvitation.EligibilitySource.IMPORT,
        }
        if not eligibility:
            defaults.update(
                attendance_status=Guest.RSVPStatus.PENDING,
                response_source="",
                responded_at=None,
            )
        GuestEventInvitation.objects.update_or_create(
            guest=guest,
            event=event,
            defaults=defaults,
        )


@transaction.atomic
def apply_batch(batch):
    batch = GuestImportBatch.objects.select_for_update().get(pk=batch.pk)
    if batch.status == GuestImportBatch.Status.APPLIED:
        return batch
    if batch.status != GuestImportBatch.Status.ANALYZED:
        raise ValidationError("Cet import n'est pas prêt à être confirmé.")

    response_time = timezone.now()
    valid_rows = batch.rows.select_related("matched_guest").filter(
        outcome__in=[GuestImportRow.Outcome.NEW, GuestImportRow.Outcome.MATCHED]
    )
    for row in valid_rows:
        parsed = {field: change["new"] for field, change in row.proposed_changes.items()}
        guest = row.matched_guest
        if guest:
            guest = Guest.objects.select_for_update().get(pk=guest.pk)
            for field, value in parsed.items():
                if field != "city_hall_eligible":
                    setattr(guest, field, value)
            if "rsvp_status" in parsed:
                guest.rsvp_source = Guest.RSVPSource.EXCEL
                guest.rsvp_responded_at = response_time
            guest.full_clean()
            guest.save()
        else:
            values = {field: value for field, value in parsed.items() if field != "city_hall_eligible"}
            values["email"] = values.get("email") or None
            values["guest_type"] = Guest.GuestType.REGULAR
            values["rsvp_source"] = Guest.RSVPSource.EXCEL
            values["rsvp_responded_at"] = response_time
            guest = Guest(**values)
            guest.full_clean()
            guest.save()
            row.matched_guest = guest
            row.save(update_fields=["matched_guest"])

        full_parsed = _parse_row(row.sheet_name, row.row_number, row.raw_data)[1]
        _apply_event_invitations(guest, full_parsed, response_time)
        GuestSourceRecord.objects.update_or_create(
            source="excel",
            external_key=row.source_key,
            defaults={"guest": guest, "last_seen_batch": batch},
        )

    batch.status = GuestImportBatch.Status.APPLIED
    batch.applied_at = response_time
    batch.save(update_fields=["status", "applied_at"])
    return batch
