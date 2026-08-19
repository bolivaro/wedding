import hashlib
import io
import json
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from ..models import Guest, Ticket


class TicketGenerationError(Exception):
    pass


def party_members(primary_guest):
    if primary_guest.invitation_owner_id:
        primary_guest = primary_guest.invitation_owner
    companions = primary_guest.companions.filter(is_active=True).order_by(
        "first_name",
        "last_name",
    )
    return [primary_guest, *companions]


def party_rsvp_complete(primary_guest):
    if primary_guest.invitation_owner_id:
        primary_guest = primary_guest.invitation_owner
    if primary_guest.rsvp_status != Guest.RSVPStatus.ATTENDING:
        return False
    eligible = primary_guest.event_invitations.filter(
        is_eligible=True,
        event__is_active=True,
    )
    return eligible.exists() and not eligible.filter(
        attendance_status=Guest.RSVPStatus.PENDING,
    ).exists()


def qr_payload(guest):
    path = reverse("guests:public_qr_landing", kwargs={"token": guest.qr_token})
    return f"{settings.SITE_BASE_URL.rstrip('/')}{path}"


def _template_path():
    resolved = finders.find(settings.TICKET_TEMPLATE_STATIC_PATH)
    if not resolved:
        raise TicketGenerationError(
            f"Gabarit de billet introuvable : {settings.TICKET_TEMPLATE_STATIC_PATH}"
        )
    return Path(resolved)


def _font_path():
    resolved = finders.find(settings.TICKET_FONT_STATIC_PATH)
    if not resolved:
        raise TicketGenerationError(
            f"Police de billet introuvable : {settings.TICKET_FONT_STATIC_PATH}"
        )
    return Path(resolved)


def _template_checksum(template_path):
    digest = hashlib.sha256()
    with template_path.open("rb") as template_file:
        for chunk in iter(lambda: template_file.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_signature(guest):
    payload = {
        "gender": guest.gender,
        "first_name": guest.first_name.strip(),
        "last_name": guest.last_name.strip(),
        "qr_token": str(guest.qr_token),
        "font_static_path": settings.TICKET_FONT_STATIC_PATH,
        "font_checksum": _template_checksum(_font_path()),
        "name_center_x": settings.TICKET_NAME_CENTER_X,
        "name_top_y": settings.TICKET_NAME_TOP_Y,
        "name_font_ratio": settings.TICKET_NAME_FONT_RATIO,
        "qr_center_x": settings.TICKET_QR_CENTER_X,
        "qr_top_y": settings.TICKET_QR_TOP_Y,
        "qr_size_ratio": settings.TICKET_QR_SIZE_RATIO,
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def ticket_is_current(ticket, guest, *, template_checksum=None):
    if not ticket.is_ready:
        return False
    if template_checksum is None:
        template_checksum = _template_checksum(_template_path())
    return (
        ticket.template_version == settings.TICKET_TEMPLATE_VERSION
        and ticket.template_checksum == template_checksum
        and ticket.render_signature == _render_signature(guest)
    )


def _fit_font(draw, text, max_width, initial_size, font_path):
    size = max(18, initial_size)
    while size > 18:
        font = ImageFont.truetype(font_path, size=size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(font_path, size=18)


def _render_ticket_images(guest, template_path):
    with Image.open(template_path) as source:
        image = source.convert("RGB").copy()

    width, height = image.size
    draw = ImageDraw.Draw(image)
    display_name = " ".join(
        part for part in (guest.salutation, guest.first_name, guest.last_name.upper()) if part
    )
    font = _fit_font(
        draw,
        display_name,
        int(width * 0.76),
        int(height * settings.TICKET_NAME_FONT_RATIO),
        _font_path(),
    )
    name_x = int(width * settings.TICKET_NAME_CENTER_X)
    name_y = int(height * settings.TICKET_NAME_TOP_Y)
    draw.text(
        (name_x, name_y),
        display_name,
        font=font,
        fill="#4b4035",
        anchor="ma",
        align="center",
    )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4,
    )
    qr.add_data(qr_payload(guest))
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="#4b4035", back_color="#fffaf1").convert("RGB")
    qr_size = int(min(width, height) * settings.TICKET_QR_SIZE_RATIO)
    qr_image = qr_image.resize((qr_size, qr_size), Image.Resampling.NEAREST)
    qr_x = int(width * settings.TICKET_QR_CENTER_X - qr_size / 2)
    qr_y = int(height * settings.TICKET_QR_TOP_Y)
    image.paste(qr_image, (qr_x, qr_y))

    jpg_buffer = io.BytesIO()
    image.save(jpg_buffer, format="JPEG", quality=94, optimize=True, dpi=(300, 300))
    pdf_buffer = io.BytesIO()
    image.save(pdf_buffer, format="PDF", resolution=300.0)
    return jpg_buffer.getvalue(), pdf_buffer.getvalue()


def generate_ticket(guest, *, force=False):
    if not guest.is_active:
        raise TicketGenerationError("Impossible de générer le billet d'un invité inactif.")

    ticket, _ = Ticket.objects.get_or_create(guest=guest)
    template_path = _template_path()
    checksum = _template_checksum(template_path)
    signature = _render_signature(guest)
    if not force and ticket_is_current(ticket, guest, template_checksum=checksum):
        return ticket

    try:
        jpg_content, pdf_content = _render_ticket_images(guest, template_path)
        file_stem = f"billet-{settings.TICKET_TEMPLATE_VERSION}-{signature[:12]}"
        ticket.jpg_file.save(
            f"{file_stem}.jpg",
            ContentFile(jpg_content),
            save=False,
        )
        ticket.pdf_file.save(
            f"{file_stem}.pdf",
            ContentFile(pdf_content),
            save=False,
        )
        ticket.status = Ticket.Status.READY
        ticket.template_version = settings.TICKET_TEMPLATE_VERSION
        ticket.template_checksum = checksum
        ticket.render_signature = signature
        ticket.generated_at = timezone.now()
        ticket.last_error = ""
        ticket.save()
    except Exception as exc:
        ticket.status = Ticket.Status.FAILED
        ticket.last_error = str(exc)[:2000]
        ticket.save(update_fields=["status", "last_error", "updated_at"])
        raise TicketGenerationError("La génération du billet a échoué.") from exc
    return ticket


def generate_party_tickets(primary_guest, *, force=False):
    return [generate_ticket(guest, force=force) for guest in party_members(primary_guest)]


def build_party_pdf(primary_guest):
    tickets = generate_party_tickets(primary_guest)
    images = []
    try:
        for ticket in tickets:
            ticket.jpg_file.open("rb")
            with Image.open(ticket.jpg_file) as source:
                images.append(source.convert("RGB").copy())
            ticket.jpg_file.close()
        output = io.BytesIO()
        images[0].save(
            output,
            format="PDF",
            save_all=True,
            append_images=images[1:],
            resolution=300.0,
        )
        return output.getvalue()
    finally:
        for image in images:
            image.close()
