from urllib.parse import quote_plus

from django.conf import settings
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.utils.translation import get_language, gettext as translate, gettext_lazy as _

from guests.models import GuestEventInvitation, WeddingEvent
from guests.services.access import get_session_guest
from guests.services.event_messages import YOUNG_CHILDREN_PROGRAM_MESSAGE

from .models import Accommodation, StayArea
from .services.stay_recommendations import recommend_area, selected_event_codes


DRESS_CODE_THEMES = [
    {
        "slug": "terre-brulee",
        "name": _("Terre brûlée"),
        "subtitle": _("Brique · Brun clair"),
        "description": _("Des tons chaleureux et profonds, inspirés des feuilles d'automne."),
        "swatches": [(_("Brique"), "#C04657"), (_("Brun clair"), "#C8A27A")],
    },
    {
        "slug": "vert-nature",
        "name": _("Verdoyant"),
        "subtitle": _("Olive · Vert nature"),
        "description": _("Une palette végétale, élégante et facile à associer aux tons naturels."),
        "swatches": [(_("Olive"), "#6F7050"), (_("Vert nature"), "#3F5545")],
    },
    {
        "slug": "sable-dore",
        "name": _("Sable doré"),
        "subtitle": _("Beige sable · Moutarde"),
        "description": _("Des nuances lumineuses et douces pour apporter une touche solaire."),
        "swatches": [(_("Beige sable"), "#D6C3A5"), (_("Moutarde"), "#C89A2B")],
    },
    {
        "slug": "gris-elegant",
        "name": _("Gris élégant"),
        "subtitle": _("Perle · Anthracite"),
        "description": _("Des neutres raffinés qui équilibrent naturellement les couleurs chaudes."),
        "swatches": [(_("Perle"), "#B8B3AA"), (_("Anthracite"), "#4B4B49")],
    },
]

PROGRAM_ICON_ASSETS = {
    WeddingEvent.EventIcon.CITY_HALL: "guests/images/program-icons/city-hall.svg",
    WeddingEvent.EventIcon.CHURCH: "guests/images/program-icons/church.svg",
    WeddingEvent.EventIcon.TOAST: "guests/images/program-icons/toast.svg",
    WeddingEvent.EventIcon.DINNER: "guests/images/program-icons/dinner.svg",
}

# Editorial copy seeded in the database remains stored in French. Marking it here
# lets the presentation layer localize known values without altering production data.
DATABASE_COPY = (
    _("Cérémonie civile"), _("Cérémonie religieuse"), _("Vin d'honneur"), _("Dîner"),
    _("Le début officiel de notre journée, entourés de nos proches."),
    _("Un temps de célébration et de partage au cœur de Puteaux."),
    _("Retrouvons-nous autour d'un verre avant de poursuivre les festivités."),
    _("Dîner, surprises et soirée dansante pour célébrer ensemble."),
    _("Puteaux & La Défense"), _("Ris-Orangis & environs"), _("Sud parisien, compromis voiture"),
    _("Priorité aux cérémonies"), _("Priorité à la soirée"), _("Compromis entre les lieux"),
    _("Une base pratique pour rejoindre rapidement la mairie, l'église et le vin d'honneur."),
    _("Offre de transports et de logements variée, commerces et restauration à proximité."),
    _("Prévoyez le trajet vers Ris-Orangis après les cérémonies."),
    _("Particulièrement adaptée aux invités privilégiant les transports en commun."),
    _("Une option confortable pour limiter le trajet de retour après le dîner et la soirée."),
    _("Retour plus simple en fin de soirée, notamment en voiture ou en taxi."),
    _("Les cérémonies du matin se déroulent à Puteaux, plus au nord."),
    _("Vérifiez les horaires de transport tardifs et les possibilités de stationnement."),
    _("Une zone intermédiaire à envisager pour équilibrer les déplacements entre Puteaux et Ris-Orangis."),
    _("Répartition plus équilibrée des kilomètres sur l'ensemble de la journée."),
    _("La circulation peut modifier fortement les durées : comparez chaque trajet avant de réserver."),
    _("Option surtout pertinente pour les invités disposant d'une voiture."),
)


def _localize_fields(instance, *field_names):
    for field_name in field_names:
        value = getattr(instance, field_name, "")
        if value:
            setattr(instance, field_name, translate(value))


def _public_context(request, **extra):
    guest = get_session_guest(request)
    return {"session_guest": guest, **extra}


def _events():
    events = list(WeddingEvent.objects.filter(is_active=True).order_by("display_order", "starts_at", "name"))
    for event in events:
        event.icon_asset = PROGRAM_ICON_ASSETS.get(event.icon, "")
        _localize_fields(event, "name", "description")
    return events


def _embed_url(address):
    key = settings.GOOGLE_MAPS_EMBED_API_KEY
    if not key or not address:
        return ""
    return f"https://www.google.com/maps/embed/v1/place?key={quote_plus(key)}&q={quote_plus(address)}&language={get_language()}&region=fr"


def home(request):
    slides = [
        {"eyebrow": _("17 octobre 2026"), "title": _("Une journée à célébrer ensemble"), "text": _("Toutes les informations utiles pour préparer votre venue."), "image": "website/images/carousel/proposal-hand.webp", "image_width": 2200, "image_height": 2200},
        {"eyebrow": _("Notre histoire"), "title": _("Quelques souvenirs, bientôt ici"), "text": _("Les images et les mots de cette galerie seront ajoutés prochainement."), "image": "website/images/carousel/proposal-bir.webp", "image_width": 2600, "image_height": 1734},
        {"eyebrow": _("Votre séjour"), "title": _("Préparez chaque étape sereinement"), "text": _("Programme, tenue, trajets et conseils de logement réunis au même endroit."), "image": "website/images/carousel/couple-goal.webp", "image_width": 2600, "image_height": 1734},
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
    return render(
        request,
        "website/program.html",
        _public_context(
            request,
            events=events,
            young_children_message=YOUNG_CHILDREN_PROGRAM_MESSAGE,
        ),
    )


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
    for area in areas:
        _localize_fields(
            area, "name", "summary", "advantages", "considerations",
            "transport_notes", "recommended_for",
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
