import hashlib
import io
import json
import textwrap
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from lesbon.public_urls import build_public_url, normalize_public_url
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from ..models import Guest, GuestEventInvitation, Ticket, WeddingEvent
from .event_messages import YOUNG_CHILDREN_TICKET_MESSAGE


INFO_BACKGROUND = "#FFEEEC"
INFO_TERRACOTTA = "#B12200"
INFO_TERRACOTTA_DARK = "#781700"
INFO_GOLD = "#CD9241"
INFO_TEXT = "#4B4035"
CITY_HALL_PRIVACY_MESSAGE = (
    "En raison de la capacité limitée de la salle, la cérémonie civile se déroulera "
    "dans la stricte intimité familiale. Merci de vous référer à votre invitation."
)

DRESS_CODE_PALETTES = (
    ("Terre brûlée", (("Brique", "#C04657"), ("Brun clair", "#C8A27A"))),
    ("Verdoyant", (("Olive", "#6F7050"), ("Vert nature", "#3F5545"))),
    ("Sable doré", (("Beige sable", "#D6C3A5"), ("Moutarde", "#C89A2B"))),
    ("Gris élégant", (("Perle", "#B8B3AA"), ("Anthracite", "#4B4B49"))),
)

PROGRAM_ICON_ASSETS = {
    WeddingEvent.EventIcon.CITY_HALL: {
        "source": "guests/images/program-icons/city-hall.svg",
        "raster": "guests/images/program-icons/city-hall.png",
    },
    WeddingEvent.EventIcon.CHURCH: {
        "source": "guests/images/program-icons/church.svg",
        "raster": "guests/images/program-icons/church.png",
    },
    WeddingEvent.EventIcon.TOAST: {
        "source": "guests/images/program-icons/toast.svg",
        "raster": "guests/images/program-icons/toast.png",
    },
    WeddingEvent.EventIcon.DINNER: {
        "source": "guests/images/program-icons/dinner.svg",
        "raster": "guests/images/program-icons/dinner.png",
    },
}


class TicketGenerationError(Exception):
    pass


def get_primary_guest(guest):
    return guest.invitation_owner if guest.invitation_owner_id else guest


def party_members(primary_guest):
    primary_guest = get_primary_guest(primary_guest)
    companions = primary_guest.companions.filter(is_active=True).order_by(
        "first_name",
        "last_name",
    )
    return [primary_guest, *companions]


def party_rsvp_complete(primary_guest):
    primary_guest = get_primary_guest(primary_guest)
    if primary_guest.rsvp_status != Guest.RSVPStatus.ATTENDING:
        return False
    eligible = primary_guest.event_invitations.filter(
        is_eligible=True,
        event__is_active=True,
        event__requires_rsvp=True,
    )
    return eligible.exists() and not eligible.filter(
        attendance_status=Guest.RSVPStatus.PENDING,
    ).exists()


def qr_payload(guest):
    guest = get_primary_guest(guest)
    path = reverse("guests:public_qr_landing", kwargs={"token": guest.qr_token})
    return build_public_url(
        path,
        base_url=settings.SITE_BASE_URL,
        debug=settings.DEBUG,
    )


def _public_information_url(configured_url, fallback_path):
    return normalize_public_url(
        configured_url,
        fallback_path=fallback_path,
        base_url=settings.SITE_BASE_URL,
        debug=settings.DEBUG,
    )


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


def _info_font_path():
    resolved = finders.find(settings.TICKET_INFO_FONT_STATIC_PATH)
    if not resolved:
        raise TicketGenerationError(
            f"Police d'informations introuvable : {settings.TICKET_INFO_FONT_STATIC_PATH}"
        )
    return Path(resolved)


def _template_checksum(template_path):
    digest = hashlib.sha256()
    with template_path.open("rb") as template_file:
        for chunk in iter(lambda: template_file.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_signature(guest):
    guest = get_primary_guest(guest)
    members = party_members(guest)
    payload = {
        "ticket_mode": "party",
        "members": [
            {
                "id": member.pk,
                "gender": member.gender,
                "first_name": member.first_name.strip(),
                "last_name": member.last_name.strip(),
            }
            for member in members
        ],
        "qr_token": str(guest.qr_token),
        "font_static_path": settings.TICKET_FONT_STATIC_PATH,
        "font_checksum": _template_checksum(_font_path()),
        "info_font_static_path": settings.TICKET_INFO_FONT_STATIC_PATH,
        "info_font_checksum": _template_checksum(_info_font_path()),
        "reference_size": [
            settings.TICKET_REFERENCE_WIDTH,
            settings.TICKET_REFERENCE_HEIGHT,
        ],
        "name_box": settings.TICKET_NAME_BOX,
        "name_font_points": settings.TICKET_NAME_FONT_POINTS,
        "name_color": settings.TICKET_NAME_COLOR,
        "qr_box": settings.TICKET_QR_BOX,
        "qr_foreground": settings.TICKET_QR_FOREGROUND,
        "qr_background": settings.TICKET_QR_BACKGROUND,
        "output_dpi": settings.TICKET_OUTPUT_DPI,
        "wedding_date": settings.WEDDING_DATE.isoformat(),
        "program_url": _public_information_url(
            settings.WEDDING_PROGRAM_URL,
            "programme/",
        ),
        "dress_code_url": _public_information_url(
            settings.WEDDING_DRESS_CODE_URL,
            "dress-code/",
        ),
        "dress_code_palettes": DRESS_CODE_PALETTES,
        # Increment whenever the generated information-page geometry changes so
        # already stored PDFs are regenerated instead of serving stale artwork.
        "information_layout_version": 6,
        "program": _program_snapshot(_ticket_program_events(guest)),
        "program_icon_assets": _program_icon_assets_snapshot(),
    }
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def ticket_is_current(ticket, guest, *, template_checksum=None):
    guest = get_primary_guest(guest)
    if not ticket.is_ready:
        return False
    if template_checksum is None:
        template_checksum = _template_checksum(_template_path())
    return (
        ticket.template_version == settings.TICKET_TEMPLATE_VERSION
        and ticket.template_checksum == template_checksum
        and ticket.render_signature == _render_signature(guest)
    )


def _scaled_box(box, *, width, height):
    scale_x = width / settings.TICKET_REFERENCE_WIDTH
    scale_y = height / settings.TICKET_REFERENCE_HEIGHT
    left, top, right, bottom = box
    return (
        round(left * scale_x),
        round(top * scale_y),
        round(right * scale_x),
        round(bottom * scale_y),
    )


def _initial_name_font_size(member_count, *, height):
    base_size = round(
        settings.TICKET_NAME_FONT_POINTS
        * settings.TICKET_OUTPUT_DPI
        / 72
        * height
        / settings.TICKET_REFERENCE_HEIGHT
    )
    reductions = {1: 0, 2: 4, 3: 8, 4: 12, 5: 16}
    reduction = reductions.get(member_count, 16 + (member_count - 5) * 2)
    return max(24, base_size - reduction)


def _fit_font(draw, text, max_width, max_height, initial_size, font_path):
    size = max(12, initial_size)
    while size >= 12:
        font = ImageFont.truetype(font_path, size=size)
        spacing = max(4, round(size * 0.2))
        bounds = draw.multiline_textbbox(
            (0, 0),
            text,
            font=font,
            spacing=spacing,
            align="center",
        )
        if bounds[2] - bounds[0] <= max_width and bounds[3] - bounds[1] <= max_height:
            return font, spacing, bounds
        size -= 1
    raise TicketGenerationError(
        "Les identités des invités ne peuvent pas tenir dans la zone du billet."
    )


def _member_display_name(member):
    return " ".join(
        part
        for part in (member.salutation, member.first_name, member.last_name.upper())
        if part
    )


def _make_qr_image(payload, *, max_size):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=1,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    total_modules = qr.modules_count + (qr.border * 2)
    module_size = max_size // total_modules
    if module_size < 2:
        raise TicketGenerationError("La zone réservée au QR code est trop petite.")
    qr.box_size = module_size
    return qr.make_image(
        fill_color=settings.TICKET_QR_FOREGROUND,
        back_color=settings.TICKET_QR_BACKGROUND,
    ).convert("RGB")


def _program_events():
    return list(WeddingEvent.objects.filter(is_active=True).order_by("display_order", "name"))


def _program_snapshot(events=None):
    return [
        {
            "code": event.code,
            "name": event.name,
            "venue_name": event.venue_name,
            "address": event.address,
            "map_url": event.map_url,
            "icon": event.icon,
            "starts_at": event.starts_at.isoformat() if event.starts_at else None,
            "display_order": event.display_order,
        }
        for event in (events if events is not None else _program_events())
    ]


def _ticket_program_events(primary_guest):
    members = party_members(primary_guest)
    invitations = list(
        GuestEventInvitation.objects.filter(
            guest__in=members,
            is_eligible=True,
            event__is_active=True,
        ).select_related("guest", "event")
    )
    if not invitations:
        return _program_events()
    names_by_event = {}
    events_by_id = {}
    for invitation in invitations:
        events_by_id[invitation.event_id] = invitation.event
        names_by_event.setdefault(invitation.event_id, []).append(
            invitation.guest.first_name or invitation.guest.full_name
        )
    for event_id, event in events_by_id.items():
        invited_names = names_by_event[event_id]
        event.invitation_note = "Pour : " + " · ".join(invited_names)
    return sorted(events_by_id.values(), key=lambda event: (event.display_order, event.name))


def _program_icon_asset_path(icon, variant):
    asset = PROGRAM_ICON_ASSETS.get(icon)
    if not asset:
        return None
    static_path = asset[variant]
    resolved = finders.find(static_path)
    if not resolved:
        raise TicketGenerationError(
            f"Pictogramme de programme introuvable : {static_path}"
        )
    return Path(resolved)


def _program_icon_assets_snapshot():
    return [
        {
            "icon": icon,
            "source": asset["source"],
            "source_checksum": _template_checksum(
                _program_icon_asset_path(icon, "source")
            ),
            "raster": asset["raster"],
            "raster_checksum": _template_checksum(
                _program_icon_asset_path(icon, "raster")
            ),
        }
        for icon, asset in PROGRAM_ICON_ASSETS.items()
    ]


def _format_wedding_date():
    months = (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    )
    wedding_date = settings.WEDDING_DATE
    return f"{wedding_date.day} {months[wedding_date.month - 1]} {wedding_date.year}"


def _event_time_label(event):
    if event.starts_at is None:
        return "Horaire à confirmer"
    local_start = timezone.localtime(event.starts_at)
    return f"{local_start:%H} h {local_start:%M}"


def _centered_text(draw, *, width, y, text, font, fill):
    bounds = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (bounds[2] - bounds[0])) / 2, y), text, font=font, fill=fill)


def _paste_event_icon(image, icon, box):
    asset_path = _program_icon_asset_path(icon, "raster")
    if asset_path is None:
        return False

    left, top, right, bottom = box
    max_width = max(1, round(right - left))
    max_height = max(1, round(bottom - top))
    with Image.open(asset_path) as source:
        rendered = source.convert("RGBA")
        rendered.thumbnail(
            (max_width, max_height),
            resample=Image.Resampling.LANCZOS,
        )
    position = (
        round(left + (max_width - rendered.width) / 2),
        round(top + (max_height - rendered.height) / 2),
    )
    image.paste(rendered, position, rendered)
    return True


def _draw_event_icon(draw, icon, box, *, color=INFO_GOLD):
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    stroke = max(4, round(min(width, height) * 0.055))

    def point(x, y):
        return (left + width * x / 100, top + height * y / 100)

    def line(points, line_width=stroke):
        draw.line(
            [point(x, y) for x, y in points],
            fill=color,
            width=line_width,
            joint="curve",
        )

    def ellipse(bounds, line_width=stroke):
        x1, y1, x2, y2 = bounds
        draw.ellipse(
            (*point(x1, y1), *point(x2, y2)),
            outline=color,
            width=line_width,
        )

    if icon == WeddingEvent.EventIcon.CITY_HALL:
        line([(8, 34), (50, 12), (92, 34), (92, 43), (8, 43), (8, 34)])
        ellipse((44, 20, 56, 32), max(3, stroke - 1))
        line([(16, 45), (16, 84), (84, 84), (84, 45)])
        for column_x in (28, 43, 57, 72):
            line([(column_x, 46), (column_x, 83)], max(3, stroke - 1))
        line([(10, 85), (90, 85), (90, 94), (10, 94), (10, 85)])
        return True

    if icon == WeddingEvent.EventIcon.CHURCH:
        line([(50, 4), (50, 20)])
        line([(44, 10), (56, 10)])
        line([(28, 35), (50, 18), (72, 35)])
        line([(33, 34), (33, 88), (67, 88), (67, 34)])
        line([(8, 52), (28, 40), (33, 48)])
        line([(67, 48), (72, 40), (92, 52)])
        line([(12, 51), (12, 88), (88, 88), (88, 51)])
        ellipse((44, 38, 56, 50), max(3, stroke - 1))
        draw.rounded_rectangle(
            (*point(43, 67), *point(57, 88)),
            radius=max(4, round(width * 0.07)),
            outline=color,
            width=max(3, stroke - 1),
        )
        line([(7, 90), (93, 90)])
        return True

    if icon == WeddingEvent.EventIcon.TOAST:
        line([(14, 18), (43, 28), (47, 48), (42, 62), (33, 70), (23, 68), (16, 58), (12, 40), (14, 18)])
        line([(86, 18), (57, 28), (53, 48), (58, 62), (67, 70), (77, 68), (84, 58), (88, 40), (86, 18)])
        line([(19, 44), (45, 44)])
        line([(55, 44), (81, 44)])
        line([(33, 70), (26, 91)])
        line([(67, 70), (74, 91)])
        line([(18, 93), (31, 93)])
        line([(69, 93), (82, 93)])
        line([(50, 5), (50, 15)])
        line([(40, 10), (45, 16)], max(3, stroke - 1))
        line([(60, 10), (55, 16)], max(3, stroke - 1))
        return True

    if icon == WeddingEvent.EventIcon.DINNER:
        ellipse((25, 15, 78, 82))
        ellipse((35, 27, 68, 70), max(3, stroke - 1))
        line([(10, 18), (10, 78), (7, 92), (13, 92), (10, 78)])
        for tine_x in (5, 10, 15):
            line([(tine_x, 18), (tine_x, 36)], max(2, stroke - 2))
        line([(89, 18), (89, 92)])
        line([(89, 18), (82, 48), (89, 48)])
        line([(44, 45), (50, 40), (56, 45), (56, 51), (50, 58), (44, 51), (44, 45)], max(3, stroke - 1))
        return True

    if icon == WeddingEvent.EventIcon.PARTY:
        ellipse((12, 28, 60, 82))
        line([(36, 28), (36, 82)], max(3, stroke - 1))
        line([(13, 55), (59, 55)], max(3, stroke - 1))
        line([(70, 25), (70, 70), (83, 66)])
        ellipse((62, 65, 72, 76), max(3, stroke - 1))
        ellipse((81, 60, 91, 71), max(3, stroke - 1))
        line([(70, 25), (88, 21), (88, 66)])
        return True

    return False


def _render_information_image(events=None):
    width = settings.TICKET_REFERENCE_WIDTH
    height = settings.TICKET_REFERENCE_HEIGHT
    image = Image.new("RGB", (width, height), INFO_BACKGROUND)
    draw = ImageDraw.Draw(image)
    info_font = _info_font_path()
    title_font = _font_path()
    font = lambda size: ImageFont.truetype(info_font, size=size)
    title = lambda size: ImageFont.truetype(title_font, size=size)

    _centered_text(
        draw,
        width=width,
        y=105,
        text="Informations pratiques",
        font=title(90),
        fill=INFO_TERRACOTTA,
    )
    _centered_text(
        draw,
        width=width,
        y=215,
        text=f"Leslie & Bolivar · {_format_wedding_date()}",
        font=font(40),
        fill=INFO_GOLD,
    )
    _centered_text(
        draw,
        width=width,
        y=278,
        text="Les dernières informations resteront mises à jour en ligne",
        font=title(30),
        fill=INFO_TEXT,
    )

    planning_box = (145, 375, 1651, 1365)
    draw.rounded_rectangle(planning_box, radius=36, outline=INFO_GOLD, width=4)
    draw.text((220, 430), "Le programme", font=title(62), fill=INFO_TERRACOTTA_DARK)
    events = list(events if events is not None else _program_events())
    if not events:
        draw.text(
            (220, 590),
            "Le programme sera publié prochainement.",
            font=font(40),
            fill=INFO_TEXT,
        )
    else:
        rows_top = 555
        has_city_hall = any(event.code == WeddingEvent.Code.CITY_HALL for event in events)
        rows_bottom = 1130 if has_city_hall else 1285
        row_height = (rows_bottom - rows_top) / max(1, len(events))
        event_title_size = max(28, min(39, round(row_height * 0.22)))
        event_detail_size = max(23, min(30, round(row_height * 0.16)))
        map_links = []
        for index, event in enumerate(events):
            row_top = round(rows_top + index * row_height)
            event_icon = getattr(event, "icon", "")
            icon_drawn = _paste_event_icon(
                image,
                event_icon,
                (205, row_top - 6, 320, row_top + 116),
            )
            if not icon_drawn and event_icon == WeddingEvent.EventIcon.PARTY:
                icon_drawn = _draw_event_icon(
                    draw,
                    event_icon,
                    (205, row_top - 6, 320, row_top + 116),
                )
            if not icon_drawn:
                circle_size = max(58, min(80, round(row_height * 0.45)))
                circle_box = (220, row_top, 220 + circle_size, row_top + circle_size)
                draw.ellipse(circle_box, fill=INFO_TERRACOTTA)
                number = f"{index + 1:02d}"
                number_font = font(max(22, round(circle_size * 0.36)))
                number_bounds = draw.textbbox((0, 0), number, font=number_font)
                draw.text(
                    (
                        220 + (circle_size - (number_bounds[2] - number_bounds[0])) / 2,
                        row_top + (circle_size - (number_bounds[3] - number_bounds[1])) / 2 - 5,
                    ),
                    number,
                    font=number_font,
                    fill=INFO_BACKGROUND,
                )
            text_x = 355
            event_title = f"{_event_time_label(event)} · {event.name}"
            draw.text(
                (text_x, row_top - 3),
                event_title,
                font=font(event_title_size),
                fill=INFO_TEXT,
            )
            venue_name = event.venue_name or "Lieu à confirmer"
            draw.text(
                (text_x, row_top + event_title_size + 10),
                venue_name,
                font=font(event_detail_size),
                fill=INFO_TEXT,
            )
            address = event.address or "Adresse à confirmer"
            address_y = row_top + event_title_size + event_detail_size + 22
            draw.text(
                (text_x, address_y),
                address,
                font=font(max(22, event_detail_size - 2)),
                fill=INFO_TERRACOTTA if event.map_url else INFO_TEXT,
            )
            invitation_note = getattr(event, "invitation_note", "")
            if invitation_note:
                note_top = address_y + event_detail_size + 7
                note_font, _, note_bounds = _fit_font(
                    draw,
                    invitation_note,
                    1160,
                    28,
                    22,
                    info_font,
                )
                note_width = note_bounds[2] - note_bounds[0]
                note_box = (
                    text_x - 10,
                    note_top - 3,
                    text_x + note_width + 18,
                    note_top + 28,
                )
                draw.rounded_rectangle(
                    note_box,
                    radius=14,
                    fill="#F3E5CF",
                )
                draw.text(
                    (text_x, note_top),
                    invitation_note,
                    font=note_font,
                    fill=INFO_TERRACOTTA_DARK,
                )
            if event.map_url and event.address:
                map_links.append(
                    {
                        "box": (
                            text_x,
                            address_y,
                            1550,
                            address_y + event_detail_size + 12,
                        ),
                        "url": event.map_url,
                    }
                )
            if index < len(events) - 1:
                # Keep the separator below the personalized “Pour : …” pill.
                line_y = round(row_top + row_height - 4)
                draw.line((text_x, line_y, 1550, line_y), fill=INFO_GOLD, width=2)

    notice_cards = []
    if events and any(event.code == WeddingEvent.Code.CITY_HALL for event in events):
        notice_cards.append(
            (
                "À propos de la mairie",
                CITY_HALL_PRIVACY_MESSAGE,
            )
        )
    if events and any(event.code == WeddingEvent.Code.RECEPTION for event in events):
        notice_cards.append(
            (
                "À propos des jeunes enfants",
                YOUNG_CHILDREN_TICKET_MESSAGE,
            )
        )
    notice_width = 1385 if len(notice_cards) == 1 else 675
    for notice_index, (notice_title, notice_text) in enumerate(notice_cards):
        notice_left = 205 + notice_index * 700
        notice_box = (notice_left, 1160, notice_left + notice_width, 1315)
        draw.rounded_rectangle(
            notice_box,
            radius=24,
            fill="#F8DDD4",
            outline="#E7B6A5",
            width=2,
        )
        draw.text(
            (notice_left + 30, 1183),
            notice_title,
            font=title(27),
            fill=INFO_TERRACOTTA_DARK,
        )
        draw.multiline_text(
            (notice_left + 30, 1222),
            textwrap.fill(notice_text, width=55 if len(notice_cards) > 1 else 105),
            font=font(20 if len(notice_cards) > 1 else 22),
            fill=INFO_TEXT,
            spacing=6,
        )

    dress_box = (145, 1425, 1651, 2045)
    draw.rounded_rectangle(dress_box, radius=36, outline=INFO_TERRACOTTA, width=4)
    draw.text((220, 1480), "Le dress code", font=title(62), fill=INFO_TERRACOTTA_DARK)
    draw.text(
        (220, 1565),
        "Une tenue élégante, festive et chaleureuse",
        font=font(38),
        fill=INFO_TEXT,
    )
    draw.text((220, 1640), "Aperçu de la palette", font=font(35), fill=INFO_GOLD)
    for palette_index, (palette_name, shades) in enumerate(DRESS_CODE_PALETTES):
        row, column = divmod(palette_index, 2)
        group_left = 220 + column * 680
        group_top = 1690 + row * 155
        draw.text(
            (group_left, group_top),
            palette_name,
            font=title(29),
            fill=INFO_TERRACOTTA_DARK,
        )
        for shade_index, (label, color) in enumerate(shades):
            left = group_left + shade_index * 290
            swatch_top = group_top + 43
            swatch_box = (left, swatch_top, left + 230, swatch_top + 58)
            draw.rounded_rectangle(
                swatch_box,
                radius=18,
                fill=color,
                outline=color,
                width=3,
            )
            label_font = font(23)
            label_bounds = draw.textbbox((0, 0), label, font=label_font)
            draw.text(
                (left + 115 - (label_bounds[2] - label_bounds[0]) / 2, swatch_top + 66),
                label,
                font=label_font,
                fill=INFO_TEXT,
            )
    _centered_text(
        draw,
        width=width,
        y=2005,
        text="Retrouvez les inspirations de tenues sur la page Dress code.",
        font=title(28),
        fill=INFO_TEXT,
    )

    program_button = (170, 2140, 858, 2285)
    dress_button = (938, 2140, 1626, 2285)
    buttons = (
        (program_button, "Consulter le programme", INFO_TERRACOTTA),
        (dress_button, "Découvrir le dress code", INFO_TERRACOTTA_DARK),
    )
    for box, label, color in buttons:
        draw.rounded_rectangle(box, radius=34, fill=color)
        button_font = font(35)
        label_bounds = draw.textbbox((0, 0), label, font=button_font)
        draw.text(
            (
                (box[0] + box[2] - (label_bounds[2] - label_bounds[0])) / 2,
                (box[1] + box[3] - (label_bounds[3] - label_bounds[1])) / 2 - 7,
            ),
            label,
            font=button_font,
            fill=INFO_BACKGROUND,
        )
    _centered_text(
        draw,
        width=width,
        y=2365,
        text="Les informations définitives resteront disponibles en ligne.",
        font=title(28),
        fill=INFO_TEXT,
    )

    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=96,
        subsampling=0,
        optimize=True,
        dpi=(settings.TICKET_OUTPUT_DPI, settings.TICKET_OUTPUT_DPI),
    )
    return buffer.getvalue(), {
        "program": program_button,
        "dress_code": dress_button,
        "maps": map_links if events else [],
    }


def _pdf_link_box(pixel_box):
    page_width, page_height = A4
    reference_width = settings.TICKET_REFERENCE_WIDTH
    reference_height = settings.TICKET_REFERENCE_HEIGHT
    left, top, right, bottom = pixel_box
    return (
        left / reference_width * page_width,
        (reference_height - bottom) / reference_height * page_height,
        right / reference_width * page_width,
        (reference_height - top) / reference_height * page_height,
    )


def _build_two_page_pdf(ticket_jpg, information_jpg, link_boxes):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    page_width, page_height = A4
    pdf.setTitle("Billet de mariage — Leslie & Bolivar")
    pdf.drawImage(
        ImageReader(io.BytesIO(ticket_jpg)),
        0,
        0,
        width=page_width,
        height=page_height,
    )
    pdf.showPage()
    pdf.drawImage(
        ImageReader(io.BytesIO(information_jpg)),
        0,
        0,
        width=page_width,
        height=page_height,
    )
    pdf.linkURL(
        _public_information_url(settings.WEDDING_PROGRAM_URL, "programme/"),
        _pdf_link_box(link_boxes["program"]),
        relative=0,
        thickness=0,
    )
    pdf.linkURL(
        _public_information_url(settings.WEDDING_DRESS_CODE_URL, "dress-code/"),
        _pdf_link_box(link_boxes["dress_code"]),
        relative=0,
        thickness=0,
    )
    for map_link in link_boxes.get("maps", []):
        pdf.linkURL(
            map_link["url"],
            _pdf_link_box(map_link["box"]),
            relative=0,
            thickness=0,
        )
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _render_ticket_images(guest, template_path):
    guest = get_primary_guest(guest)
    with Image.open(template_path) as source:
        image = source.convert("RGB").copy()

    width, height = image.size
    draw = ImageDraw.Draw(image)
    members = party_members(guest)
    display_names = "\n".join(_member_display_name(member) for member in members)
    name_box = _scaled_box(settings.TICKET_NAME_BOX, width=width, height=height)
    inner_width = max(1, name_box[2] - name_box[0] - round(width * 0.045))
    inner_height = max(1, name_box[3] - name_box[1] - round(height * 0.016))
    font, spacing, bounds = _fit_font(
        draw,
        display_names,
        inner_width,
        inner_height,
        _initial_name_font_size(len(members), height=height),
        _font_path(),
    )
    name_center_x = (name_box[0] + name_box[2]) / 2
    name_center_y = (name_box[1] + name_box[3]) / 2
    name_x = name_center_x - (bounds[0] + bounds[2]) / 2
    name_y = name_center_y - (bounds[1] + bounds[3]) / 2
    draw.multiline_text(
        (name_x, name_y),
        display_names,
        font=font,
        fill=settings.TICKET_NAME_COLOR,
        align="center",
        spacing=spacing,
    )

    qr_box = _scaled_box(settings.TICKET_QR_BOX, width=width, height=height)
    qr_image = _make_qr_image(
        qr_payload(guest),
        max_size=min(qr_box[2] - qr_box[0], qr_box[3] - qr_box[1]),
    )
    qr_x = qr_box[0] + (qr_box[2] - qr_box[0] - qr_image.width) // 2
    qr_y = qr_box[1] + (qr_box[3] - qr_box[1] - qr_image.height) // 2
    image.paste(qr_image, (qr_x, qr_y))

    jpg_buffer = io.BytesIO()
    image.save(
        jpg_buffer,
        format="JPEG",
        quality=96,
        subsampling=0,
        optimize=True,
        dpi=(settings.TICKET_OUTPUT_DPI, settings.TICKET_OUTPUT_DPI),
    )
    jpg_content = jpg_buffer.getvalue()
    information_jpg, link_boxes = _render_information_image(_ticket_program_events(guest))
    pdf_content = _build_two_page_pdf(jpg_content, information_jpg, link_boxes)
    return jpg_content, pdf_content


def generate_ticket(guest, *, force=False):
    guest = get_primary_guest(guest)
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
        file_stem = f"billet-groupe-{settings.TICKET_TEMPLATE_VERSION}-{signature[:12]}"
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


def build_party_pdf(primary_guest):
    ticket = generate_ticket(primary_guest)
    ticket.pdf_file.open("rb")
    try:
        return ticket.pdf_file.read()
    finally:
        ticket.pdf_file.close()


def build_information_jpg():
    information_jpg, _ = _render_information_image()
    return information_jpg
