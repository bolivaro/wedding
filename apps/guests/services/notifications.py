import base64

from django.conf import settings
from django.utils.html import escape

from lesbon.email import get_brevo_sender, send_brevo_email
from lesbon.public_urls import build_public_url

from guests.models import Guest


def _absolute_url(path):
    return build_public_url(
        path,
        base_url=settings.SITE_BASE_URL,
        debug=settings.DEBUG,
    )


def send_email_verification(*, issued_token):
    token = issued_token.token
    path = f"/invites/email/verify/{token.selector}/{issued_token.secret}/"
    link = _absolute_url(path)
    escaped_name = escape(token.guest.first_name)
    escaped_link = escape(link)
    send_brevo_email(
        to=[{"email": token.target_email, "name": token.guest.full_name}],
        subject="Vérifiez votre adresse email",
        text_content=(
            f"Bonjour {token.guest.first_name},\n\n"
            "Confirmez votre adresse email en ouvrant le lien ci-dessous :\n\n"
            f"{link}\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
        ),
        html_content=(
            '<div style="font-family:Arial,sans-serif;color:#4a403b;line-height:1.6">'
            f"<p>Bonjour {escaped_name},</p>"
            "<p>Confirmez votre adresse email en cliquant sur ce bouton :</p>"
            '<p style="margin:24px 0">'
            f'<a href="{escaped_link}" '
            'style="display:inline-block;padding:12px 20px;border-radius:10px;'
            'background:#b65f45;color:#fff;text-decoration:none;font-weight:700">'
            "Vérifier mon adresse email</a></p>"
            "<p>Si le bouton ne fonctionne pas, copiez cette adresse dans votre navigateur :</p>"
            f'<p><a href="{escaped_link}">{escaped_link}</a></p>'
            "<p>Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.</p>"
            "</div>"
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


def send_rsvp_notification(*, guest):
    guest = Guest.objects.prefetch_related(
        "companions",
        "event_invitations__event",
    ).get(pk=guest.pk)
    attending = guest.rsvp_status == Guest.RSVPStatus.ATTENDING
    response_label = "Présence confirmée" if attending else "Absence confirmée"

    event_lines = []
    for invitation in guest.event_invitations.all():
        if not invitation.event.is_active or not invitation.event.requires_rsvp:
            continue
        event_lines.append(
            f"- {invitation.event.name} : {invitation.get_attendance_status_display()}"
        )
    companion_lines = [
        f"- {companion.full_name} — {companion.age_category_label or 'tranche d’âge non renseignée'}"
        for companion in guest.companions.all()
        if companion.is_active
    ]
    text_content = (
        f"{response_label} pour {guest.full_name}.\n\n"
        f"Réponse globale : {guest.get_rsvp_status_display()}\n\n"
        f"Tranche d’âge : {guest.age_category_label or 'non renseignée'}\n\n"
        "Réponses par événement :\n"
        f"{chr(10).join(event_lines) or '- Aucun événement soumis au RSVP'}\n\n"
        "Accompagnants :\n"
        f"{chr(10).join(companion_lines) or '- Aucun accompagnant'}"
    )
    recipients = [
        {"email": email}
        for email in settings.RSVP_NOTIFICATION_EMAILS
        if email
    ]
    if not recipients:
        return None
    return send_brevo_email(
        to=recipients,
        subject=f"[RSVP] {response_label} — {guest.full_name}",
        text_content=text_content,
        reply_to=(
            {"email": guest.email, "name": guest.full_name}
            if guest.email and guest.email_verified_at
            else get_brevo_sender()
        ),
    )


def send_ticket_email(*, guest, pdf_content):
    if not guest.email or not guest.email_verified_at:
        raise ValueError("Une adresse email vérifiée est requise pour envoyer les billets.")
    send_brevo_email(
        to=[{"email": guest.email, "name": guest.full_name}],
        subject="Votre billet pour notre mariage",
        text_content=(
            f"Bonjour {guest.first_name},\n\n"
            "Vous trouverez en pièce jointe le billet de votre invitation. "
            "Son QR code unique permettra d'identifier tout votre groupe.\n\n"
            "Gardez votre lien RSVP privé : le QR du billet sert uniquement à "
            "retrouver les informations utiles le jour du mariage."
        ),
        reply_to=get_brevo_sender(),
        attachments=[
            {
                "name": "billet-groupe-mariage.pdf",
                "content": base64.b64encode(pdf_content).decode("ascii"),
            }
        ],
    )
