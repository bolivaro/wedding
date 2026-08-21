from django.core.exceptions import ValidationError
from django.db import transaction

from guests.models import Guest, GuestEventInvitation
from guests.services.deadline import is_rsvp_open


@transaction.atomic
def add_companion(*, primary_guest, first_name, last_name, gender, age_category):
    if not is_rsvp_open():
        raise ValidationError("La date limite RSVP est dépassée.")
    primary_guest = Guest.objects.select_for_update().get(pk=primary_guest.pk)
    if primary_guest.invitation_owner_id:
        raise ValidationError("Seul un invité principal peut ajouter des accompagnants.")
    if age_category not in Guest.AgeCategory.values:
        raise ValidationError("La tranche d’âge de l’accompagnant est invalide.")

    active_count = primary_guest.companions.filter(is_active=True).count()
    if active_count >= primary_guest.companion_limit:
        raise ValidationError("Le nombre maximal d'accompagnants est atteint.")

    companion = Guest.objects.create(
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        gender=gender,
        age_category=age_category,
        guest_type=Guest.GuestType.REGULAR,
        guest_group=primary_guest.guest_group,
        invitation_owner=primary_guest,
        rsvp_status=(
            Guest.RSVPStatus.ATTENDING
            if primary_guest.rsvp_status == Guest.RSVPStatus.ATTENDING
            else Guest.RSVPStatus.PENDING
        ),
        rsvp_source=Guest.RSVPSource.GUEST,
    )

    event_invitations = []
    for invitation in primary_guest.event_invitations.select_related("event"):
        status = Guest.RSVPStatus.PENDING
        if invitation.is_eligible and invitation.attendance_status == Guest.RSVPStatus.ATTENDING:
            status = Guest.RSVPStatus.ATTENDING
        event_invitations.append(
            GuestEventInvitation(
                guest=companion,
                event=invitation.event,
                is_eligible=invitation.is_eligible,
                attendance_status=status,
                response_source=Guest.RSVPSource.GUEST if status != Guest.RSVPStatus.PENDING else "",
            )
        )
    GuestEventInvitation.objects.bulk_create(event_invitations)
    return companion


@transaction.atomic
def update_companion(*, primary_guest, companion, first_name, last_name, gender, age_category):
    if not is_rsvp_open():
        raise ValidationError("La date limite RSVP est dépassée.")
    if age_category not in Guest.AgeCategory.values:
        raise ValidationError("La tranche d’âge de l’accompagnant est invalide.")

    companion = Guest.objects.select_for_update().get(
        pk=companion.pk,
        invitation_owner=primary_guest,
        is_active=True,
    )
    companion.first_name = first_name.strip()
    companion.last_name = last_name.strip()
    companion.gender = gender
    companion.age_category = age_category
    companion.save(
        update_fields=["first_name", "last_name", "gender", "age_category", "updated_at"]
    )
    return companion


@transaction.atomic
def deactivate_companion(*, primary_guest, companion):
    if not is_rsvp_open():
        raise ValidationError("La date limite RSVP est dépassée.")
    companion = Guest.objects.select_for_update().get(
        pk=companion.pk,
        invitation_owner=primary_guest,
    )
    companion.is_active = False
    companion.rsvp_status = Guest.RSVPStatus.NOT_ATTENDING
    companion.rsvp_source = Guest.RSVPSource.GUEST
    companion.save(update_fields=["is_active", "rsvp_status", "rsvp_source", "updated_at"])
    companion.event_invitations.update(
        attendance_status=Guest.RSVPStatus.NOT_ATTENDING,
        response_source=Guest.RSVPSource.GUEST,
    )
    return companion
