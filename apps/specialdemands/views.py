from urllib.parse import quote

from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import SpecialDemand


def home(request):
    return render(request, "specialdemands/home.html")


def special_demand_detail(request, token):
    demand = get_object_or_404(
        SpecialDemand.objects.select_related("guest").prefetch_related("slides"),
        token=token
    )

    return render(
        request,
        "specialdemands/detail.html",
        {
            "demand": demand,
            "slides": demand.slides.all(),
        },
    )


def special_demand_respond(request, token):
    demand = get_object_or_404(
        SpecialDemand.objects.select_related("guest"),
        token=token
    )

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if request.method != "POST":
        if is_ajax:
            return JsonResponse({"error": "Méthode non autorisée."}, status=405)
        return redirect("specialdemands:detail", token=demand.token)

    if demand.status != "pending":
        if is_ajax:
            return JsonResponse({"status": demand.status}, status=200)
        return redirect("specialdemands:detail", token=demand.token)

    decision = request.POST.get("decision")

    if decision not in ["accepted", "declined"]:
        if is_ajax:
            return JsonResponse({"error": "Décision invalide."}, status=400)
        return redirect("specialdemands:detail", token=demand.token)

    demand.status = decision
    demand.responded_at = timezone.now()
    demand.save()

    send_notification_email_to_couple(demand)
    send_confirmation_email_to_guest(demand)

    if is_ajax:
        return JsonResponse(
            {
                "status": demand.status,
                "responded_at": demand.responded_at.isoformat(),
            }
        )

    return redirect("specialdemands:detail", token=demand.token)


def send_notification_email_to_couple(demand):
    subject = f"Réponse à une demande spéciale - {demand.guest.full_name}"
    status_label = "accepté" if demand.status == "accepted" else "refusé"

    message = (
        f"{demand.guest.full_name} a {status_label} la demande de "
        f"{demand.get_demand_type_display().lower()}.\n\n"
        f"Email: {demand.guest.email}\n"
        f"Répondu le: {demand.responded_at.strftime('%d/%m/%Y à %H:%M') if demand.responded_at else 'N/A'}\n"
    )

    recipients = []

    if getattr(settings, "SPECIAL_DEMAND_DEFAULT_NOTIFY_EMAILS", None):
        recipients.extend(settings.SPECIAL_DEMAND_DEFAULT_NOTIFY_EMAILS)

    if demand.notify_emails:
        extra_emails = [
            email.strip()
            for email in demand.notify_emails.split(",")
            if email.strip()
        ]
        recipients.extend(extra_emails)

    recipients = list(dict.fromkeys(recipients))

    if recipients:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )


def build_whatsapp_link(phone_number, message):
    """
    phone_number doit être au format international sans '+' ni espaces.
    Exemple : 33612345678
    """
    return f"https://wa.me/{phone_number}?text={quote(message)}"


def get_guest_confirmation_content(demand):
    guest_first_name = demand.guest.first_name
    demand_type = demand.demand_type
    demand_type_label = demand.get_demand_type_display().lower()
    is_accepted = demand.status == "accepted"
    is_declined = demand.status == "declined"
    is_witness_accepted = is_accepted and demand_type == "witness"

    whatsapp_message = (
        f"Bonjour Leslie et Bolivar, "
        f"je vous envoie ma pièce d'identité suite à mon acceptation "
        f"de votre demande de témoin."
    )

    if is_witness_accepted:
        subject = "Merci pour ta réponse 💛 Petite étape pour la mairie"
        title = "Merci infiniment 💛"
        intro = (
            f"Nous avons bien reçu ta réponse concernant notre demande de "
            f"<strong>{demand_type_label}</strong>."
        )
        response_box_text = "Tu as accepté d’être notre témoin."
        closing = (
            "Merci du fond du cœur. Cela nous touche énormément et nous sommes "
            "très heureux de pouvoir partager cette aventure avec toi."
        )
    elif is_accepted and demand_type == "best_man":
        subject = "Merci pour ta réponse 💛"
        title = "Merci infiniment 💛"
        intro = (
            f"Nous avons bien reçu ta réponse concernant notre demande "
            f"d’<strong>homme d’honneur</strong>."
        )
        response_box_text = "Tu as accepté cette demande."
        closing = (
            "Merci du fond du cœur. Nous sommes très heureux de te compter à nos côtés "
            "pour ce moment si important."
        )
    elif is_accepted and demand_type == "maid_of_honor":
        subject = "Merci pour ta réponse 💛"
        title = "Merci infiniment 💛"
        intro = (
            f"Nous avons bien reçu ta réponse concernant notre demande de "
            f"<strong>femme d’honneur</strong>."
        )
        response_box_text = "Tu as accepté cette demande."
        closing = (
            "Merci du fond du cœur. Nous sommes très heureux de te compter à nos côtés "
            "pour ce moment si important."
        )
    elif is_declined and demand_type == "witness":
        subject = "Confirmation de réception de ta réponse"
        title = "Merci pour ta réponse"
        intro = (
            f"Nous avons bien reçu ta réponse concernant notre demande de "
            f"<strong>{demand_type_label}</strong>."
        )
        response_box_text = "Tu as refusé cette demande."
        closing = (
            "Merci d’avoir pris le temps de nous répondre. On t’embrasse fort "
            "et on est heureux de te compter parmi les personnes importantes de notre vie."
        )
    elif is_declined and demand_type in ["best_man", "maid_of_honor"]:
        subject = "Confirmation de réception de ta réponse"
        title = "Merci pour ta réponse"
        intro = (
            f"Nous avons bien reçu ta réponse concernant notre demande de "
            f"<strong>{demand_type_label}</strong>."
        )
        response_box_text = "Tu as refusé cette demande."
        closing = (
            "Merci d’avoir pris le temps de nous répondre. Cela ne change rien à l’affection "
            "que nous avons pour toi."
        )
    else:
        subject = "Confirmation de réception de ta réponse"
        title = "Merci pour ta réponse"
        intro = (
            f"Nous avons bien reçu ta réponse concernant notre demande de "
            f"<strong>{demand_type_label}</strong>."
        )
        response_box_text = (
            "Tu as accepté cette demande." if is_accepted else "Tu as refusé cette demande."
        )
        closing = "Merci beaucoup pour ta réponse."

    context = {
        "guest_first_name": guest_first_name,
        "title": title,
        "intro": intro,
        "response_box_text": response_box_text,
        "closing": closing,
        "is_witness_accepted": is_witness_accepted,
        "whatsapp_link_1": build_whatsapp_link(
            settings.WHATSAPP_NUMBER_1,
            whatsapp_message
        ),
        "whatsapp_link_2": build_whatsapp_link(
            settings.WHATSAPP_NUMBER_2,
            whatsapp_message
        ),
        "whatsapp_label_1": getattr(settings, "WHATSAPP_LABEL_1", "Leslie"),
        "whatsapp_label_2": getattr(settings, "WHATSAPP_LABEL_2", "Bolivar"),
        "reply_to_email": getattr(settings, "SPECIAL_DEMAND_REPLY_TO_EMAIL", settings.DEFAULT_FROM_EMAIL),
    }

    return subject, context


def send_confirmation_email_to_guest(demand):
    subject, context = get_guest_confirmation_content(demand)

    text_content = render_to_string(
        "specialdemands/emails/guest_confirmation.txt",
        context
    )
    html_content = render_to_string(
        "specialdemands/emails/guest_confirmation.html",
        context
    )

    reply_to_email = getattr(
        settings,
        "SPECIAL_DEMAND_REPLY_TO_EMAIL",
        settings.DEFAULT_FROM_EMAIL
    )

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[demand.guest.email],
        reply_to=[reply_to_email],
    )
    email.attach_alternative(html_content, "text/html")
    email.send(fail_silently=False)