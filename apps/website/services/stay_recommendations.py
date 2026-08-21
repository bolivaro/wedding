from dataclasses import dataclass

from guests.models import Guest, WeddingEvent


@dataclass(frozen=True)
class StayRecommendation:
    area_slug: str
    title: str
    explanation: str


def selected_event_codes(guest):
    if guest is None:
        return []
    invitations = guest.event_invitations.select_related("event").filter(
        is_eligible=True,
        event__is_active=True,
    )
    attending = [
        invitation.event.code
        for invitation in invitations
        if invitation.attendance_status == Guest.RSVPStatus.ATTENDING
    ]
    if attending:
        return attending
    return [invitation.event.code for invitation in invitations]


def recommend_area(event_codes, priority="balanced"):
    codes = set(event_codes)
    reception = WeddingEvent.Code.RECEPTION in codes
    ceremonies = bool(codes & {WeddingEvent.Code.CITY_HALL, WeddingEvent.Code.CHURCH})

    if priority == "evening" or (reception and not ceremonies):
        return StayRecommendation(
            "ris-orangis",
            "Privilégiez la proximité de la soirée",
            "Cette zone limite le trajet de retour après le dîner et les festivités.",
        )
    if priority == "ceremonies" or (ceremonies and not reception):
        return StayRecommendation(
            "puteaux-la-defense",
            "Privilégiez Puteaux et La Défense",
            "Vous serez au plus près des cérémonies et du vin d'honneur.",
        )
    return StayRecommendation(
        "compromis-sud-parisien",
        "Recherchez un compromis entre les lieux",
        "Vous prévoyez plusieurs étapes : comparez les trajets réels dans Google Maps avant de réserver.",
    )
