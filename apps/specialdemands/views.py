from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

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

    if request.method != "POST":
        return redirect("specialdemands:detail", token=demand.token)

    if demand.status != "pending":
        return redirect("specialdemands:detail", token=demand.token)

    decision = request.POST.get("decision")

    if decision not in ["accepted", "declined"]:
        return redirect("specialdemands:detail", token=demand.token)

    demand.status = decision
    demand.responded_at = timezone.now()
    demand.save()

    send_notification_email_to_couple(demand)
    send_confirmation_email_to_guest(demand)

    return redirect("specialdemands:detail", token=demand.token)


def send_notification_email_to_couple(demand):
    subject = f"Réponse à une demande spéciale - {demand.guest.full_name}"
    status_label = "accepté" if demand.status == "accepted" else "refusé"

    message = (
        f"{demand.guest.full_name} a {status_label} la demande de "
        f"{demand.get_demand_type_display().lower()}.\n\n"
        f"Email: {demand.guest.email}\n"
        f"Répondu le: {demand.responded_at}\n"
    )

    recipients = []

    if getattr(settings, "SPECIAL_DEMAND_DEFAULT_NOTIFY_EMAILS", None):
        recipients.extend(settings.SPECIAL_DEMAND_DEFAULT_NOTIFY_EMAILS)

    if demand.notify_emails:
        extra_emails = [email.strip() for email in demand.notify_emails.split(",") if email.strip()]
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


def send_confirmation_email_to_guest(demand):
    subject = "Confirmation de réception de ta réponse"
    status_label = "accepté" if demand.status == "accepted" else "refusé"

    message = (
        f"Bonjour {demand.guest.first_name},\n\n"
        f"Nous avons bien reçu ta réponse concernant notre demande de "
        f"{demand.get_demand_type_display().lower()}.\n"
        f"Tu as {status_label} cette demande.\n\n"
        f"Merci beaucoup pour ta réponse.\n"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[demand.guest.email],
        fail_silently=False,
    )