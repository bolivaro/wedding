import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)


def get_brevo_sender():
    sender_email = getattr(settings, "BREVO_SENDER_EMAIL", None) or getattr(
        settings,
        "DEFAULT_FROM_EMAIL_ADDRESS",
        None,
    ) or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if not sender_email:
        raise ValueError("BREVO_SENDER_EMAIL manquant dans les settings.")
    return {
        "email": sender_email,
        "name": getattr(settings, "BREVO_SENDER_NAME", "Leslie & Bolivar"),
    }


def send_brevo_email(
    *,
    to,
    subject,
    text_content=None,
    html_content=None,
    reply_to=None,
    cc=None,
    bcc=None,
    attachments=None,
):
    api_key = getattr(settings, "BREVO_API_KEY", None)
    if not api_key:
        raise ValueError("BREVO_API_KEY manquant dans les settings.")
    if not to:
        raise ValueError("Aucun destinataire fourni.")

    payload = {"sender": get_brevo_sender(), "to": to, "subject": subject}
    for key, value in {
        "textContent": text_content,
        "htmlContent": html_content,
        "replyTo": reply_to,
        "cc": cc,
        "bcc": bcc,
        "attachment": attachments,
    }.items():
        if value:
            payload[key] = value

    request = Request(
        url="https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": api_key,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Brevo HTTPError %s: %s", exc.code, error_body)
        raise
    except URLError:
        logger.exception("Brevo URLError lors de l'envoi d'email")
        raise
