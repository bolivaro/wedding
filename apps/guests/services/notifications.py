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


class RSVPNotificationKind:
    PROVISIONAL = "provisional"
    INDIVIDUAL_CONFIRMED = "individual_confirmed"
    DECLINED = "declined"
    COMPOSITION_CONFIRMED = "composition_confirmed"
    COMPOSITION_UPDATED = "composition_updated"
    AVAILABILITY_UPDATED = "availability_updated"


def _default_rsvp_notification_kind(guest):
    if guest.rsvp_status == Guest.RSVPStatus.NOT_ATTENDING:
        return RSVPNotificationKind.DECLINED
    if guest.party_size_limit == 1:
        return RSVPNotificationKind.INDIVIDUAL_CONFIRMED
    if guest.confirmed_party_size is None:
        return RSVPNotificationKind.PROVISIONAL
    return RSVPNotificationKind.AVAILABILITY_UPDATED


def send_rsvp_notification(*, guest, notification_kind=None, previous_party_size=None):
    guest = Guest.objects.prefetch_related(
        "companions",
        "event_invitations__event",
    ).get(pk=guest.pk)
    attending = guest.rsvp_status == Guest.RSVPStatus.ATTENDING
    notification_kind = notification_kind or _default_rsvp_notification_kind(guest)
    labels = {
        RSVPNotificationKind.PROVISIONAL: ("[RSVP provisoire]", "Présence enregistrée"),
        RSVPNotificationKind.INDIVIDUAL_CONFIRMED: ("[RSVP définitif]", "Présence confirmée"),
        RSVPNotificationKind.DECLINED: ("[RSVP définitif]", "Absence confirmée"),
        RSVPNotificationKind.COMPOSITION_CONFIRMED: ("[RSVP définitif]", "Composition confirmée"),
        RSVPNotificationKind.COMPOSITION_UPDATED: ("[RSVP mis à jour]", "Composition mise à jour"),
        RSVPNotificationKind.AVAILABILITY_UPDATED: ("[RSVP mis à jour]", "Disponibilités mises à jour"),
    }
    subject_prefix, response_label = labels[notification_kind]

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
    decline_lines = ""
    if not attending:
        decline_lines = (
            "\n\nMotif de l’absence : "
            f"{guest.get_decline_reason_display() or 'non renseigné'}\n"
            "Message : "
            f"{guest.decline_message or '- Aucun message'}"
        )
    active_companion_count = len(companion_lines)
    if notification_kind == RSVPNotificationKind.PROVISIONAL:
        composition_lines = (
            "Composition du groupe : EN COURS DE SAISIE\n"
            "Ne pas considérer l’absence actuelle d’accompagnant comme définitive.\n"
            f"Accompagnants actuellement renseignés : {active_companion_count} "
            f"sur {guest.companion_limit} place(s) disponible(s)."
        )
    elif notification_kind == RSVPNotificationKind.INDIVIDUAL_CONFIRMED:
        composition_lines = "Composition définitive : 1 personne sur 1 (invitation individuelle)."
    elif notification_kind == RSVPNotificationKind.DECLINED:
        composition_lines = "Réponse définitive : l’invité principal a décliné l’invitation."
    else:
        confirmed_size = guest.confirmed_party_size or 1 + active_companion_count
        composition_lines = (
            f"Composition confirmée : {confirmed_size} personne(s) "
            f"sur {guest.party_size_limit}."
        )
        if notification_kind == RSVPNotificationKind.COMPOSITION_UPDATED and previous_party_size is not None:
            composition_lines = (
                f"Ancienne composition : {previous_party_size} personne(s).\n"
                f"Nouvelle composition : {confirmed_size} personne(s) "
                f"sur {guest.party_size_limit}."
            )
    companion_summary = chr(10).join(companion_lines)
    if not companion_summary:
        companion_summary = (
            "- Saisie non finalisée"
            if notification_kind == RSVPNotificationKind.PROVISIONAL
            else "- Aucun accompagnant"
        )
    text_content = (
        f"{response_label} pour {guest.full_name}.\n\n"
        f"Réponse globale : {guest.get_rsvp_status_display()}\n\n"
        f"Tranche d’âge : {guest.age_category_label or 'non renseignée'}\n\n"
        f"{composition_lines}\n\n"
        "Réponses par événement :\n"
        f"{chr(10).join(event_lines) or '- Aucun événement soumis au RSVP'}\n\n"
        "Accompagnants :\n"
        f"{companion_summary}"
        f"{decline_lines}"
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
        subject=f"{subject_prefix} {response_label} — {guest.full_name}",
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
