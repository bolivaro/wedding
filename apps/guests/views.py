import logging
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AccessRecoveryForm, CompanionForm, GuestEmailForm, RSVPForm
from .models import Guest, GuestEmailToken
from .services.access import (
    authenticate_guest_access,
    get_session_guest,
    issue_guest_access,
    start_guest_session,
)
from .services.companions import add_companion, deactivate_companion
from .services.deadline import is_rsvp_open
from .services.email_access import (
    consume_email_token,
    issue_recovery_token,
    request_email_verification,
)
from .services.notifications import send_access_recovery, send_email_verification
from .services.rsvp import update_rsvp


logger = logging.getLogger(__name__)


def guest_access_required(view_function):
    @wraps(view_function)
    def wrapped(request, *args, **kwargs):
        guest = get_session_guest(request)
        if guest is None:
            return redirect("guests:access_invalid")
        request.guest = guest
        return view_function(request, *args, **kwargs)

    return wrapped


def access_entry(request, selector, secret):
    credential = authenticate_guest_access(selector=selector, secret=secret)
    if credential is None:
        return redirect("guests:access_invalid")
    start_guest_session(request, credential)
    return redirect("guests:rsvp_dashboard")


def access_invalid(request):
    return render(
        request,
        "guests/access_invalid.html",
        {"support_email": settings.RSVP_SUPPORT_EMAIL},
        status=403,
    )


@guest_access_required
def rsvp_dashboard(request):
    guest = Guest.objects.prefetch_related(
        "event_invitations__event",
        "companions",
    ).get(pk=request.guest.pk)
    event_invitations = list(
        guest.event_invitations.select_related("event").filter(event__is_active=True)
    )
    eligible = [invitation for invitation in event_invitations if invitation.is_eligible]
    rsvp_complete = (
        guest.rsvp_status == Guest.RSVPStatus.ATTENDING
        and bool(eligible)
        and all(
            invitation.attendance_status != Guest.RSVPStatus.PENDING
            for invitation in eligible
        )
    )
    context = {
        "guest": guest,
        "rsvp_form": RSVPForm(guest=guest),
        "companion_form": CompanionForm(),
        "email_form": GuestEmailForm(initial={"email": guest.pending_email or guest.email}),
        "event_invitations": event_invitations,
        "active_companions": guest.companions.filter(is_active=True),
        "rsvp_open": is_rsvp_open(),
        "rsvp_complete": rsvp_complete,
        "deadline": settings.RSVP_DEADLINE,
        "support_email": settings.RSVP_SUPPORT_EMAIL,
    }
    return render(request, "guests/rsvp_dashboard.html", context)


@require_POST
@guest_access_required
def rsvp_respond(request):
    form = RSVPForm(request.POST, guest=request.guest)
    if form.is_valid():
        try:
            update_rsvp(
                guest=request.guest,
                status=form.cleaned_data["status"],
                event_responses=form.event_responses(),
            )
        except ValidationError as exc:
            for error in exc.messages:
                form.add_error(None, error)
        else:
            messages.success(request, "Votre réponse a bien été enregistrée.")
            return redirect("guests:rsvp_dashboard")

    messages.error(request, "Certaines réponses doivent être corrigées.")
    return _render_dashboard_with_form(request, form)


def _render_dashboard_with_form(request, form):
    guest = Guest.objects.prefetch_related("event_invitations__event", "companions").get(
        pk=request.guest.pk
    )
    return render(
        request,
        "guests/rsvp_dashboard.html",
        {
            "guest": guest,
            "rsvp_form": form,
            "companion_form": CompanionForm(),
            "email_form": GuestEmailForm(initial={"email": guest.pending_email or guest.email}),
            "event_invitations": guest.event_invitations.select_related("event").filter(
                event__is_active=True
            ),
            "active_companions": guest.companions.filter(is_active=True),
            "rsvp_open": is_rsvp_open(),
            "rsvp_complete": False,
            "deadline": settings.RSVP_DEADLINE,
            "support_email": settings.RSVP_SUPPORT_EMAIL,
        },
        status=400,
    )


@require_POST
@guest_access_required
def companion_add(request):
    form = CompanionForm(request.POST)
    if form.is_valid():
        try:
            add_companion(primary_guest=request.guest, **form.cleaned_data)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "L'accompagnant a été ajouté.")
    else:
        messages.error(request, "Les informations de l'accompagnant sont invalides.")
    return redirect("guests:rsvp_dashboard")


@require_POST
@guest_access_required
def companion_remove(request, companion_id):
    companion = get_object_or_404(
        Guest,
        pk=companion_id,
        invitation_owner=request.guest,
        is_active=True,
    )
    try:
        deactivate_companion(primary_guest=request.guest, companion=companion)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "L'accompagnant a été retiré.")
    return redirect("guests:rsvp_dashboard")


@require_POST
@guest_access_required
def email_update(request):
    if not is_rsvp_open():
        messages.error(request, "La date limite est dépassée. Contactez-nous pour modifier votre email.")
        return redirect("guests:rsvp_dashboard")
    form = GuestEmailForm(request.POST)
    if form.is_valid():
        try:
            issued = request_email_verification(
                guest=request.guest,
                email=form.cleaned_data["email"],
            )
            send_email_verification(issued_token=issued)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        except Exception:
            logger.exception("Impossible d'envoyer la vérification email du guest %s", request.guest.pk)
            messages.error(request, "L'email n'a pas pu être envoyé. Merci de réessayer.")
        else:
            messages.success(request, "Un lien de vérification vient de vous être envoyé.")
    else:
        messages.error(request, "Saisissez une adresse email valide.")
    return redirect("guests:rsvp_dashboard")


def verify_email(request, selector, secret):
    try:
        token = consume_email_token(
            selector=selector,
            secret=secret,
            purpose=GuestEmailToken.Purpose.VERIFY,
        )
    except ValidationError:
        token = None
    return render(request, "guests/email_verification_result.html", {"success": token is not None})


def recovery_request(request):
    form = AccessRecoveryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        guest = Guest.objects.filter(
            email__iexact=form.cleaned_data["email"].strip(),
            email_verified_at__isnull=False,
            invitation_owner__isnull=True,
            is_active=True,
        ).first()
        if guest:
            try:
                issued = issue_recovery_token(guest=guest)
                send_access_recovery(issued_token=issued)
            except Exception:
                logger.exception("Impossible d'envoyer la récupération du guest %s", guest.pk)
        messages.success(
            request,
            "Si cette adresse vérifiée est enregistrée, un lien temporaire vient d'être envoyé.",
        )
        return redirect("guests:recovery_request")
    return render(
        request,
        "guests/recovery_request.html",
        {"form": form, "support_email": settings.RSVP_SUPPORT_EMAIL},
    )


def recovery_consume(request, selector, secret):
    token = consume_email_token(
        selector=selector,
        secret=secret,
        purpose=GuestEmailToken.Purpose.RECOVER,
    )
    if token is None:
        return redirect("guests:access_invalid")
    issued_access = issue_guest_access(guest=token.guest)
    start_guest_session(request, issued_access.credential)
    return redirect("guests:rsvp_dashboard")


@guest_access_required
def ticket_preview(request):
    guest = Guest.objects.prefetch_related("event_invitations__event").get(pk=request.guest.pk)
    eligible = guest.event_invitations.filter(is_eligible=True, event__is_active=True)
    complete = (
        guest.rsvp_status == Guest.RSVPStatus.ATTENDING
        and eligible.exists()
        and not eligible.filter(attendance_status=Guest.RSVPStatus.PENDING).exists()
    )
    if not complete:
        messages.info(request, "Terminez votre RSVP avant d'accéder à l'aperçu du billet.")
        return redirect("guests:rsvp_dashboard")
    return render(request, "guests/ticket_preview.html", {"guest": guest})


def public_qr_landing(request, token):
    guest_exists = Guest.objects.filter(qr_token=token, is_active=True).exists()
    return render(request, "guests/public_qr_landing.html", {"recognized": guest_exists})
