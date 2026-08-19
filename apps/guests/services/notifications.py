import base64

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


def send_ticket_email(*, guest, pdf_content):
    if not guest.email or not guest.email_verified_at:
        raise ValueError("Une adresse email vérifiée est requise pour envoyer les billets.")
    send_brevo_email(
        to=[{"email": guest.email, "name": guest.full_name}],
        subject="Vos billets pour notre mariage",
        text_content=(
            f"Bonjour {guest.first_name},\n\n"
            "Vous trouverez en pièce jointe les billets de votre invitation. "
            "Chaque personne dispose de son propre QR code.\n\n"
            "Gardez votre lien RSVP privé : le QR du billet sert uniquement à "
            "retrouver les informations utiles le jour du mariage."
        ),
        reply_to=get_brevo_sender(),
        attachments=[
            {
                "name": "billets-mariage.pdf",
                "content": base64.b64encode(pdf_content).decode("ascii"),
            }
        ],
    )
