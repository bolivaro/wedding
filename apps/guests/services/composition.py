from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from guests.models import Guest


def composition_is_editable(guest, *, at=None):
    now = at or timezone.now()
    if guest.invitation_owner_id or now > settings.RSVP_DEADLINE:
        return False
    if not guest.party_composition_confirmed_at:
        return True
    return bool(guest.party_composition_editable_until and now <= guest.party_composition_editable_until)


@transaction.atomic
def confirm_party_composition(*, primary_guest, come_alone=False, at=None):
    now = at or timezone.now()
    primary_guest = Guest.objects.select_for_update().get(pk=primary_guest.pk)
    if primary_guest.invitation_owner_id:
        raise ValidationError("Seul l’invité principal peut confirmer la composition.")
    if primary_guest.rsvp_status != Guest.RSVPStatus.ATTENDING:
        raise ValidationError("Confirmez d’abord votre présence avant la composition du groupe.")
    if not composition_is_editable(primary_guest, at=now):
        raise ValidationError("Le délai de modification de la composition est dépassé.")

    if come_alone:
        companions = list(primary_guest.companions.select_for_update().filter(is_active=True))
        Guest.objects.filter(pk__in=[companion.pk for companion in companions]).update(
            is_active=False,
            rsvp_status=Guest.RSVPStatus.NOT_ATTENDING,
            rsvp_source=Guest.RSVPSource.GUEST,
        )
        for companion in companions:
            companion.event_invitations.update(
                attendance_status=Guest.RSVPStatus.NOT_ATTENDING,
                response_source=Guest.RSVPSource.GUEST,
                responded_at=now,
            )

    party_size = 1 + primary_guest.companions.filter(is_active=True).count()
    if not primary_guest.party_composition_confirmed_at:
        primary_guest.party_composition_confirmed_at = now
        primary_guest.party_composition_editable_until = min(
            now + timedelta(days=settings.RSVP_COMPOSITION_EDIT_DAYS),
            settings.RSVP_DEADLINE,
        )
    primary_guest.confirmed_party_size = party_size
    primary_guest.save(
        update_fields=[
            "confirmed_party_size",
            "party_composition_confirmed_at",
            "party_composition_editable_until",
            "updated_at",
        ]
    )
    return primary_guest


def composition_state(guest, *, at=None):
    now = at or timezone.now()
    if guest.confirmed_party_size is None:
        return "pending"
    if guest.party_composition_editable_until and now <= guest.party_composition_editable_until:
        return "provisional"
    return "locked"
