from django.conf import settings

from lesbon.email import get_brevo_sender, send_brevo_email


def _absolute_url(path):
    return f"{settings.SITE_BASE_URL.rstrip('/')}{path}"


def send_email_verification(*, issued_token):
    token = issued_token.token
    path = f"/invites/email/verify/{token.selector}/{issued_token.secret}/"
    link = _absolute_url(path)
    send_brevo_email(
        to=[{"email": token.target_email, "name": token.guest.full_name}],
        subject="Vérifiez votre adresse email",
        text_content=(
            f"Bonjour {token.guest.first_name},\n\n"
            f"Confirmez votre adresse email avec ce lien : {link}\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
        ),
        reply_to=get_brevo_sender(),
    )


def send_access_recovery(*, issued_token):
    token = issued_token.token
    path = f"/invites/access/recover/{token.selector}/{issued_token.secret}/"
    link = _absolute_url(path)
    send_brevo_email(
        to=[{"email": token.target_email, "name": token.guest.full_name}],
        subject="Retrouvez votre accès RSVP",
        text_content=(
            f"Bonjour {token.guest.first_name},\n\n"
            f"Utilisez ce lien temporaire pour retrouver votre RSVP : {link}\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
        ),
        reply_to=get_brevo_sender(),
    )
