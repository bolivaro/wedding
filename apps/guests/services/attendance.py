"""Effective event responses, including global and inherited absences."""
from django.db.models import Case, CharField, Exists, F, OuterRef, Q, Value, When

from guests.models import Guest, GuestEventInvitation


def event_responses():
    owner_absent = GuestEventInvitation.objects.filter(
        guest_id=OuterRef("guest__invitation_owner_id"),
        event_id=OuterRef("event_id"),
        attendance_status=Guest.RSVPStatus.NOT_ATTENDING,
    )
    inherited_absence = Q(guest__attendance_mode=Guest.AttendanceMode.INHERIT) & (
        Q(guest__invitation_owner__rsvp_status=Guest.RSVPStatus.NOT_ATTENDING)
        | Q(owner_absent=True)
    )
    return GuestEventInvitation.objects.annotate(owner_absent=Exists(owner_absent)).annotate(
        effective_status=Case(
            When(
                Q(guest__rsvp_status=Guest.RSVPStatus.NOT_ATTENDING) | inherited_absence,
                then=Value(Guest.RSVPStatus.NOT_ATTENDING),
            ),
            default=F("attendance_status"),
            output_field=CharField(),
        )
    )


def present_responses():
    return event_responses().filter(
        guest__is_active=True,
        is_eligible=True,
        effective_status=Guest.RSVPStatus.ATTENDING,
    )
