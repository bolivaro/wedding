"""Printable A4 dinner seating documents; no files or guest data are changed."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether

from guests.models import DinnerTable, DinnerSeatingAssignment
from guests.services.seating import dinner_guests


FONT = "DinnerSeating"


def seating_export_data():
    guests = list(dinner_guests())
    confirmed = {guest.pk for guest in guests}
    assignments = list(DinnerSeatingAssignment.objects.select_related("guest", "table").order_by(
        "guest__last_name", "guest__first_name", "guest_id",
    ))
    assigned = {item.guest_id for item in assignments}
    return {
        "tables": [(table, [item.guest for item in assignments if item.table_id == table.pk and item.guest_id in confirmed])
                   for table in DinnerTable.objects.all()],
        "unassigned": [guest for guest in guests if guest.pk not in assigned],
        "anomalies": [item for item in assignments if item.guest_id not in confirmed],
        "confirmed_count": len(guests),
    }


def build_seating_pdf(*, per_table=False):
    data = seating_export_data()
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, str(Path(settings.BASE_DIR) / "apps/guests/static/guests/fonts/CormorantGaramond.ttf")))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="DinnerTitle", fontName=FONT, fontSize=25, leading=30, spaceAfter=16, textColor=colors.HexColor("#b65f3b")))
    styles.add(ParagraphStyle(name="DinnerTable", fontName=FONT, fontSize=19, leading=24, spaceAfter=10, textColor=colors.HexColor("#3f3833")))
    styles.add(ParagraphStyle(name="DinnerBody", fontName=FONT, fontSize=14, leading=19, spaceAfter=5, textColor=colors.HexColor("#3f3833")))
    story = []
    provisional = bool(data["unassigned"] or data["anomalies"])
    title = "Plan de tables — Dîner" + (" · Plan provisoire" if provisional else "")
    story.append(Paragraph(title, styles["DinnerTitle"]))
    story.append(Paragraph(f'{data["confirmed_count"]} convives confirmés · {len(data["unassigned"])} à placer · {len(data["anomalies"])} anomalies', styles["DinnerBody"]))
    generated = timezone.localtime().strftime("%d/%m/%Y à %H:%M")
    story.append(Paragraph(f"Généré le {generated}", styles["DinnerBody"]))
    story.append(Spacer(1, 18))
    if per_table:
        story.append(Paragraph("Une page par table suit ce récapitulatif.", styles["DinnerBody"]))
    if not data["tables"]:
        story.append(Paragraph("Aucune table créée.", styles["DinnerBody"]))
    for table, guests in data["tables"]:
        if per_table:
            story.append(PageBreak())
        block = [Paragraph(escape(str(table)), styles["DinnerTable"]),
                 Paragraph(f"{len(guests)} / 10 convives confirmés" + (" · Plan provisoire" if provisional else ""), styles["DinnerBody"])]
        block.extend(Paragraph(escape(guest.full_name), styles["DinnerBody"]) for guest in guests)
        if not guests:
            block.append(Paragraph("Aucun convive confirmé affecté.", styles["DinnerBody"]))
        block.append(Spacer(1, 18))
        story.append(KeepTogether(block))
    if provisional:
        story.append(PageBreak())
        story.append(Paragraph("Points à résoudre avant impression définitive", styles["DinnerTitle"]))
        if data["unassigned"]:
            story.append(Paragraph("Convives confirmés sans table", styles["DinnerTable"]))
            story.extend(Paragraph(escape(guest.full_name), styles["DinnerBody"]) for guest in data["unassigned"])
        if data["anomalies"]:
            story.append(Paragraph("Affectations exclues des listes de convives", styles["DinnerTable"]))
            story.extend(Paragraph(escape(f"{item.guest.full_name} — {item.table} : présence non confirmée ou invité inactif."), styles["DinnerBody"]) for item in data["anomalies"])
    output = BytesIO()
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 10)
        canvas.drawString(40, 24, f"Dîner · {generated}")
        canvas.drawRightString(A4[0] - 40, 24, str(doc.page))
        canvas.restoreState()
    SimpleDocTemplate(output, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=45,
                      title=title).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
