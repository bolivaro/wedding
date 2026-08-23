from urllib.parse import quote_plus

from django.conf import settings
from django.db.models import Prefetch
from django.shortcuts import redirect, render

from guests.models import GuestEventInvitation, WeddingEvent
from guests.services.access import get_session_guest

from .models import Accommodation, StayArea
from .services.stay_recommendations import recommend_area, selected_event_codes


DRESS_CODE_THEMES = [
    {
        "slug": "terre-brulee",
        "name": "Terre brûlée",
        "subtitle": "Brique · Brun clair",
        "description": "Des tons chaleureux et profonds, inspirés des feuilles d'automne.",
        "swatches": [("Brique", "#C04657"), ("Brun clair", "#C8A27A")],
    },
    {
        "slug": "vert-nature",
        "name": "Verdoyant",
        "subtitle": "Olive · Vert nature",
        "description": "Une palette végétale, élégante et facile à associer aux tons naturels.",
        "swatches": [("Olive", "#6F7050"), ("Vert nature", "#3F5545")],
    },
    {
        "slug": "sable-dore",
        "name": "Sable doré",
        "subtitle": "Beige sable · Moutarde",
        "description": "Des nuances lumineuses et douces pour apporter une touche solaire.",
        "swatches": [("Beige sable", "#D6C3A5"), ("Moutarde", "#C89A2B")],
    },
    {
        "slug": "gris-elegant",
        "name": "Gris élégant",
        "subtitle": "Perle · Anthracite",
        "description": "Des neutres raffinés qui équilibrent naturellement les couleurs chaudes.",
        "swatches": [("Perle", "#B8B3AA"), ("Anthracite", "#4B4B49")],
    },
]

PROGRAM_ICON_ASSETS = {
    WeddingEvent.EventIcon.CITY_HALL: "guests/images/program-icons/city-hall.svg",
    WeddingEvent.EventIcon.CHURCH: "guests/images/program-icons/church.svg",
    WeddingEvent.EventIcon.TOAST: "guests/images/program-icons/toast.svg",
    WeddingEvent.EventIcon.DINNER: "guests/images/program-icons/dinner.svg",
}


def _public_context(request, **extra):
    guest = get_session_guest(request)
    return {"session_guest": guest, **extra}


def _events():
    events = list(WeddingEvent.objects.filter(is_active=True).order_by("display_order", "starts_at", "name"))
    for event in events:
        event.icon_asset = PROGRAM_ICON_ASSETS.get(event.icon, "")
    return events


def _embed_url(address):
    key = settings.GOOGLE_MAPS_EMBED_API_KEY
    if not key or not address:
        return ""
    return f"https://www.google.com/maps/embed/v1/place?key={quote_plus(key)}&q={quote_plus(address)}&language=fr&region=fr"


def home(request):
    slides = [
        {"eyebrow": "17 octobre 2026", "title": "Une journée à célébrer ensemble", "text": "Toutes les informations utiles pour préparer votre venue."},
        {"eyebrow": "Notre histoire", "title": "Quelques souvenirs, bientôt ici", "text": "Les images et les mots de cette galerie seront ajoutés prochainement."},
        {"eyebrow": "Votre séjour", "title": "Préparez chaque étape sereinement", "text": "Programme, tenue, trajets et conseils de logement réunis au même endroit."},
    ]
    return render(request, "website/home.html", _public_context(request, slides=slides))


def program(request):
    guest = get_session_guest(request)
    events = _events()
    if guest:
        members = [guest, *guest.companions.filter(is_active=True)]
        invitations = GuestEventInvitation.objects.filter(
            guest__in=members,
            is_eligible=True,
            event__is_active=True,
        ).select_related("guest", "event")
        invited_by_event = {}
        for invitation in invitations:
            invited_by_event.setdefault(invitation.event_id, []).append(
                invitation.guest.full_name
            )
        for event in events:
            event.invited_members = invited_by_event.get(event.pk, [])
            event.is_in_group_invitation = bool(event.invited_members)
    for event in events:
        event.embed_url = _embed_url(event.address)
    return render(request, "website/program.html", _public_context(request, events=events))


def dress_code(request):
    return render(request, "website/dress_code.html", _public_context(request, dress_code_themes=DRESS_CODE_THEMES))


def stay(request):
    guest = get_session_guest(request)
    events = _events()
    event_codes = selected_event_codes(guest)
    recommendation = recommend_area(event_codes)
    areas = StayArea.objects.filter(is_published=True).prefetch_related(
        Prefetch("accommodations", queryset=Accommodation.objects.filter(is_published=True))
    )
    for event in events:
        event.embed_url = _embed_url(event.address)
    map_embed_url = settings.GOOGLE_MY_MAPS_EMBED_URL or (events[0].embed_url if events else "")
    return render(
        request,
        "website/stay.html",
        {
            "session_guest": guest,
            "events": events,
            "selected_event_codes": event_codes,
            "recommendation": recommendation,
            "areas": areas,
            "map_embed_url": map_embed_url,
        },
    )


def my_invitation(request):
    guest = get_session_guest(request)
    if guest:
        return redirect("guests:rsvp_dashboard")
    return render(request, "website/my_invitation.html", {"session_guest": None, "support_email": settings.RSVP_SUPPORT_EMAIL})
