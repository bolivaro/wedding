from django.conf import settings
from django.utils import timezone
from django.utils.formats import date_format


def build_invitation_share_text():
    deadline = settings.RSVP_DEADLINE
    if timezone.is_aware(deadline):
        deadline = timezone.localtime(deadline)

    wedding_date = date_format(settings.WEDDING_DATE, "j F Y")
    deadline_date = date_format(deadline, "j F Y")
    public_site_url = f"{settings.SITE_BASE_URL.rstrip('/')}/"

    return (
        "Leslie & Bolivar ont l’immense plaisir de vous convier à la "
        f"célébration de leur mariage le {wedding_date}.\n\n"
        "Découvrez le site du mariage et toutes les informations pratiques :\n"
        f"{public_site_url}\n\n"
        f"Merci de confirmer votre présence avant le {deadline_date} grâce "
        "au lien personnel ci-dessous.\n\n"
        "*Ce lien est strictement privé. Merci de ne pas le transmettre.*"
    )
