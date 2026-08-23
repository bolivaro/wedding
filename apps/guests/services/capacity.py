from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from guests.models import Guest, GuestEventInvitation, WeddingEvent
from guests.services.composition import composition_state


def attendance_is_open(event, *, at=None):
    now = at or timezone.now()
    return not event.attendance_change_deadline or now <= event.attendance_change_deadline


def event_capacity_snapshot(event, *, at=None):
    now = at or timezone.now()
    invitations = GuestEventInvitation.objects.filter(
        event=event,
        is_eligible=True,
        guest__is_active=True,
    )
    attending = invitations.filter(attendance_status=Guest.RSVPStatus.ATTENDING).count()
    pending_people = invitations.filter(attendance_status=Guest.RSVPStatus.PENDING).count()
    reserved_optional = 0
    provisional_release = 0
    released = 0
    owners = Guest.objects.filter(
        invitation_owner__isnull=True,
        is_active=True,
        event_invitations__event=event,
        event_invitations__is_eligible=True,
    ).prefetch_related("companions")
    for owner in owners:
        owner_invitation = owner.event_invitations.get(event=event)
        if owner_invitation.attendance_status == Guest.RSVPStatus.NOT_ATTENDING:
            released += owner.party_size_limit
            continue
        unused = max(0, owner.companion_limit - owner.companions.filter(is_active=True).count())
        if not unused:
            continue
        state = composition_state(owner, at=now)
        if state == "pending":
            reserved_optional += unused
        elif state == "provisional":
            provisional_release += unused
        else:
            released += unused
    capacity = event.capacity or 0
    safely_available = max(0, capacity - attending - pending_people - reserved_optional - provisional_release)
    return {
        "event": event,
        "capacity": capacity,
        "attending": attending,
        "pending": pending_people,
        "reserved_optional": reserved_optional,
        "provisional_release": provisional_release,
        "released": released,
        "available": safely_available,
    }


@transaction.atomic
def ensure_capacity(event, *, additional_attendees=1):
    event = WeddingEvent.objects.select_for_update().get(pk=event.pk)
    if event.capacity is None:
        return
    attending = GuestEventInvitation.objects.filter(
        event=event,
        is_eligible=True,
        guest__is_active=True,
        attendance_status=Guest.RSVPStatus.ATTENDING,
    ).count()
    if attending + additional_attendees > event.capacity:
        raise ValidationError(f"La capacité maximale est atteinte pour {event.name}.")


def demographic_statistics(event):
    return list(
        Guest.objects.filter(
            is_active=True,
            event_invitations__event=event,
            event_invitations__is_eligible=True,
            event_invitations__attendance_status=Guest.RSVPStatus.ATTENDING,
        )
        .values("age_category", "gender")
        .annotate(total=Count("pk"))
        .order_by("age_category", "gender")
    )
