from django.db import transaction

from guests.models import Guest, GuestEventInvitation, WeddingEvent


FAMILY_GROUPS = {
    Guest.GuestGroup.BRIDE_FAMILY,
    Guest.GuestGroup.GROOM_FAMILY,
}

HONOR_TYPES = {
    Guest.GuestType.HONOR,
    Guest.GuestType.WITNESS,
}


def companion_event_eligibility(*, primary_guest, primary_invitation):
    """Apply the default policy without broadening the primary invitation."""
    if not primary_invitation.is_eligible:
        return False
    if primary_invitation.event.code != WeddingEvent.Code.CITY_HALL:
        return True
    if primary_guest.guest_type in HONOR_TYPES:
        return False
    return primary_guest.guest_group in FAMILY_GROUPS


def primary_city_hall_eligibility(guest):
    return guest.guest_type in HONOR_TYPES or guest.guest_group in FAMILY_GROUPS


@transaction.atomic
def apply_city_hall_policy(primary_guest):
    """Explicitly apply the default policy to one party; admin overrides can follow."""
    primary_guest = Guest.objects.select_for_update().get(pk=primary_guest.pk)
    city_hall = WeddingEvent.objects.get(code=WeddingEvent.Code.CITY_HALL)
    members = [primary_guest, *primary_guest.companions.filter(is_active=True)]
    for member in members:
        eligible = (
            primary_city_hall_eligibility(primary_guest)
            if member.pk == primary_guest.pk
            else primary_city_hall_eligibility(primary_guest)
            and primary_guest.guest_type not in HONOR_TYPES
        )
        invitation, _ = GuestEventInvitation.objects.get_or_create(
            guest=member,
            event=city_hall,
        )
        invitation.is_eligible = eligible
        invitation.eligibility_source = GuestEventInvitation.EligibilitySource.POLICY
        if not eligible:
            invitation.attendance_status = Guest.RSVPStatus.NOT_ATTENDING
            invitation.response_source = Guest.RSVPSource.ADMIN
        elif invitation.attendance_status == Guest.RSVPStatus.NOT_ATTENDING:
            invitation.attendance_status = Guest.RSVPStatus.PENDING
            invitation.response_source = ""
            invitation.responded_at = None
        invitation.save()
    return members
