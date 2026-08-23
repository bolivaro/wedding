from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from guests.models import Guest, GuestEventInvitation
from guests.services.deadline import is_rsvp_open
from guests.services.capacity import attendance_is_open, ensure_capacity


@transaction.atomic
def update_rsvp(
    *,
    guest,
    status,
    age_category=None,
    event_responses=None,
    source=Guest.RSVPSource.GUEST,
    at=None,
):
    response_time = at or timezone.now()
    if source == Guest.RSVPSource.GUEST and not is_rsvp_open(at=response_time):
        existing_guest = Guest.objects.get(pk=guest.pk)
        if not existing_guest.rsvp_responded_at:
            raise ValidationError("La date limite RSVP est dépassée.")
    if status not in Guest.RSVPStatus.values or status == Guest.RSVPStatus.PENDING:
        raise ValidationError("Statut RSVP invalide.")
    if age_category is not None and age_category not in Guest.AgeCategory.values:
        raise ValidationError("La tranche d’âge de l’invité est invalide.")

    guest = Guest.objects.select_for_update().get(pk=guest.pk)
    invitations = {
        invitation.event.code: invitation
        for invitation in guest.event_invitations.select_for_update().select_related("event")
    }
    required_invitations = {
        code: invitation
        for code, invitation in invitations.items()
        if invitation.event.is_active and invitation.event.requires_rsvp
    }
    event_responses = event_responses or {}

    if status == Guest.RSVPStatus.NOT_ATTENDING:
        for invitation in invitations.values():
            if source == Guest.RSVPSource.GUEST and invitation.event.requires_rsvp and not attendance_is_open(invitation.event, at=response_time):
                raise ValidationError(f"Les disponibilités sont closes pour {invitation.event.name}.")
            invitation.attendance_status = Guest.RSVPStatus.NOT_ATTENDING
            invitation.response_source = source
            invitation.responded_at = response_time
            invitation.save(update_fields=["attendance_status", "response_source", "responded_at"])
        GuestEventInvitation.objects.filter(
            guest__invitation_owner=guest,
            guest__is_active=True,
            guest__attendance_mode=Guest.AttendanceMode.INHERIT,
        ).update(
            attendance_status=Guest.RSVPStatus.NOT_ATTENDING,
            response_source=source,
            responded_at=response_time,
        )
    else:
        attending_any_event = False
        for code, invitation in required_invitations.items():
            if source == Guest.RSVPSource.GUEST and not attendance_is_open(invitation.event, at=response_time):
                raise ValidationError(f"Les disponibilités sont closes pour {invitation.event.name}.")
            if not invitation.is_eligible:
                if event_responses.get(code) == Guest.RSVPStatus.ATTENDING:
                    raise ValidationError(f"L'invité n'est pas éligible à l'événement {invitation.event.name}.")
                continue
            event_status = event_responses.get(code)
            if event_status not in [Guest.RSVPStatus.ATTENDING, Guest.RSVPStatus.NOT_ATTENDING]:
                raise ValidationError(f"Une réponse est requise pour {invitation.event.name}.")
            inherited_companions = guest.companions.filter(
                is_active=True,
                attendance_mode=Guest.AttendanceMode.INHERIT,
                event_invitations__event=invitation.event,
                event_invitations__is_eligible=True,
            ).count()
            if event_status == Guest.RSVPStatus.ATTENDING and invitation.attendance_status != event_status:
                ensure_capacity(invitation.event, additional_attendees=1 + inherited_companions)
            attending_any_event = attending_any_event or event_status == Guest.RSVPStatus.ATTENDING
            invitation.attendance_status = event_status
            invitation.response_source = source
            invitation.responded_at = response_time
            invitation.save(update_fields=["attendance_status", "response_source", "responded_at"])
            GuestEventInvitation.objects.filter(
                guest__invitation_owner=guest,
                guest__is_active=True,
                guest__attendance_mode=Guest.AttendanceMode.INHERIT,
                event=invitation.event,
                is_eligible=True,
            ).update(
                attendance_status=event_status,
                response_source=source,
                responded_at=response_time,
            )
        if required_invitations and not attending_any_event:
            raise ValidationError("Au moins un événement doit être accepté pour confirmer une présence.")

        church = invitations.get("church")
        cocktail = invitations.get("cocktail")
        if church and cocktail and not cocktail.event.requires_rsvp:
            cocktail.attendance_status = (
                church.attendance_status
                if cocktail.is_eligible
                else Guest.RSVPStatus.NOT_ATTENDING
            )
            cocktail.response_source = source
            cocktail.responded_at = response_time
            cocktail.save(
                update_fields=["attendance_status", "response_source", "responded_at"]
            )

    guest.rsvp_status = status
    guest.rsvp_source = source
    guest.rsvp_responded_at = response_time
    update_fields = ["rsvp_status", "rsvp_source", "rsvp_responded_at", "updated_at"]
    if age_category is not None:
        guest.age_category = age_category
        update_fields.append("age_category")
    guest.save(update_fields=update_fields)
    return guest
