import logging
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AccessRecoveryForm, CompanionAttendanceForm, CompanionForm, GuestEmailForm, RSVPForm
from .models import Guest, GuestEmailToken
from .services.access import (
    authenticate_guest_access,
    get_session_guest,
    issue_guest_access,
    start_guest_session,
)
from .services.companions import add_companion, deactivate_companion, update_companion, update_companion_attendance
from .services.capacity import attendance_is_open
from .services.composition import confirm_party_composition, composition_is_editable, composition_state
from .services.deadline import is_rsvp_open
from .services.email_access import (
    consume_email_token,
    issue_recovery_token,
    request_email_verification,
)
from .services.notifications import (
    send_access_recovery,
    send_email_verification,
    send_rsvp_notification,
    send_ticket_email,
)
from .services.rsvp import update_rsvp
from .services.ticket import (
    TicketGenerationError,
    build_information_jpg,
    build_party_pdf,
    generate_ticket,
    party_members,
    party_rsvp_complete,
    ticket_is_current,
)


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
    return render(request, "guests/rsvp_dashboard.html", _dashboard_context(request.guest))


def _dashboard_context(
    guest,
    *,
    rsvp_form=None,
    companion_form=None,
    companion_edit_form=None,
    companion_edit_id=None,
    email_form=None,
):
    guest = Guest.objects.prefetch_related(
        "event_invitations__event",
        "companions",
    ).get(pk=guest.pk)
    event_invitations = list(
        guest.event_invitations.select_related("event").filter(
            event__is_active=True,
            event__requires_rsvp=True,
        )
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
    resolved_rsvp_form = rsvp_form if rsvp_form is not None else RSVPForm(guest=guest)
    rsvp_answered = (
        guest.rsvp_status != Guest.RSVPStatus.PENDING
        and guest.age_category in Guest.AgeCategory.values
        and (
            guest.rsvp_status == Guest.RSVPStatus.NOT_ATTENDING
            or all(
                invitation.attendance_status != Guest.RSVPStatus.PENDING
                for invitation in eligible
            )
        )
    )
    active_companions = list(guest.companions.filter(is_active=True))
    current_party_size = 1 + len(active_companions)
    composition_dirty = (
        guest.confirmed_party_size is not None
        and guest.confirmed_party_size != current_party_size
    )
    companion_rows = []
    for companion in active_companions:
        edit_form = (
            companion_edit_form
            if companion_edit_form is not None and companion.pk == companion_edit_id
            else CompanionForm(
                auto_id=f"id_companion_{companion.pk}_%s",
                initial={
                    "gender": companion.gender,
                    "first_name": companion.first_name,
                    "last_name": companion.last_name,
                    "age_category": companion.age_category,
                }
            )
        )
        attendance_form = CompanionAttendanceForm(
            companion=companion,
            auto_id=f"id_attendance_{companion.pk}_%s",
        )
        companion_rows.append((companion, edit_form, attendance_form))

    response_open = is_rsvp_open() or (
        guest.rsvp_responded_at
        and any(attendance_is_open(invitation.event) for invitation in eligible)
    )
    attendance_deadline = max(
        (invitation.event.attendance_change_deadline for invitation in eligible if invitation.event.attendance_change_deadline),
        default=None,
    )

    context = {
        "guest": guest,
        "rsvp_form": resolved_rsvp_form,
        "companion_form": companion_form if companion_form is not None else CompanionForm(),
        "email_form": email_form if email_form is not None else GuestEmailForm(initial={"email": guest.pending_email or guest.email}),
        "event_invitations": event_invitations,
        "active_companions": active_companions,
        "current_party_size": current_party_size,
        "composition_dirty": composition_dirty,
        "companion_rows": companion_rows,
        "rsvp_open": is_rsvp_open(),
        "response_open": response_open,
        "composition_editable": composition_is_editable(guest),
        "composition_state": composition_state(guest),
        "rsvp_complete": rsvp_complete,
        "rsvp_answered": rsvp_answered,
        "rsvp_editor_open": not rsvp_answered or bool(resolved_rsvp_form.errors),
        "deadline": settings.RSVP_DEADLINE,
        "attendance_deadline": attendance_deadline,
        "support_email": settings.RSVP_SUPPORT_EMAIL,
    }
    return context


def _is_async_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _fragment_response(request, *, guest, components, message, status=200, **forms):
    context = _dashboard_context(guest, **forms)
    templates = {
        "rsvp": "guests/partials/rsvp_card.html",
        "companions": "guests/partials/companions_card.html",
        "email": "guests/partials/email_card.html",
        "ticket": "guests/partials/ticket_callout.html",
    }
    fragments = {
        component: render_to_string(templates[component], context, request=request)
        for component in components
    }
    return JsonResponse(
        {"ok": status < 400, "message": message, "fragments": fragments},
        status=status,
    )


@require_POST
@guest_access_required
def rsvp_respond(request):
    form = RSVPForm(request.POST, guest=request.guest)
    if form.is_valid():
        try:
            updated_guest = update_rsvp(
                guest=request.guest,
                status=form.cleaned_data["status"],
                age_category=form.cleaned_data["age_category"],
                event_responses=form.event_responses(),
            )
        except ValidationError as exc:
            for error in exc.messages:
                form.add_error(None, error)
        else:
            try:
                send_rsvp_notification(guest=updated_guest)
            except Exception:
                logger.exception(
                    "Impossible d’envoyer la notification RSVP pour l’invité %s",
                    updated_guest.pk,
                )
            if _is_async_request(request):
                return _fragment_response(
                    request,
                    guest=request.guest,
                    components=("rsvp", "ticket"),
                    message="Votre réponse a bien été enregistrée.",
                )
            messages.success(request, "Votre réponse a bien été enregistrée.")
            return redirect("guests:rsvp_dashboard")

    if _is_async_request(request):
        return _fragment_response(
            request,
            guest=request.guest,
            components=("rsvp",),
            message="Certaines réponses doivent être corrigées.",
            status=422,
            rsvp_form=form,
        )
    messages.error(request, "Certaines réponses doivent être corrigées.")
    return _render_dashboard_with_form(request, form)


def _render_dashboard_with_form(request, form):
    return render(
        request,
        "guests/rsvp_dashboard.html",
        _dashboard_context(request.guest, rsvp_form=form),
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
            for error in exc.messages:
                form.add_error(None, error)
        else:
            if _is_async_request(request):
                return _fragment_response(
                    request,
                    guest=request.guest,
                    components=("companions", "ticket"),
                    message="L'accompagnant a été ajouté.",
                )
            messages.success(request, "L'accompagnant a été ajouté.")
            return redirect("guests:rsvp_dashboard")
    if _is_async_request(request):
        return _fragment_response(
            request,
            guest=request.guest,
            components=("companions",),
            message="Les informations de l'accompagnant sont invalides.",
            status=422,
            companion_form=form,
        )
    messages.error(
        request,
        "; ".join(form.non_field_errors()) or "Les informations de l'accompagnant sont invalides.",
    )
    return redirect("guests:rsvp_dashboard")


@require_POST
@guest_access_required
def companion_update(request, companion_id):
    companion = get_object_or_404(
        Guest,
        pk=companion_id,
        invitation_owner=request.guest,
        is_active=True,
    )
    form = CompanionForm(request.POST, auto_id=f"id_companion_{companion.pk}_%s")
    if form.is_valid():
        try:
            update_companion(
                primary_guest=request.guest,
                companion=companion,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            for error in exc.messages:
                form.add_error(None, error)
        else:
            if _is_async_request(request):
                return _fragment_response(
                    request,
                    guest=request.guest,
                    components=("companions",),
                    message="Les informations de l'accompagnant ont été mises à jour.",
                )
            messages.success(request, "Les informations de l'accompagnant ont été mises à jour.")
            return redirect("guests:rsvp_dashboard")

    if _is_async_request(request):
        return _fragment_response(
            request,
            guest=request.guest,
            components=("companions",),
            message="Les informations de l'accompagnant sont invalides.",
            status=422,
            companion_edit_form=form,
            companion_edit_id=companion.pk,
        )
    messages.error(
        request,
        "; ".join(form.non_field_errors())
        or "Les informations de l'accompagnant sont invalides.",
    )
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
        if _is_async_request(request):
            return _fragment_response(
                request,
                guest=request.guest,
                components=("companions",),
                message="; ".join(exc.messages),
                status=422,
            )
        messages.error(request, "; ".join(exc.messages))
    else:
        if _is_async_request(request):
            return _fragment_response(
                request,
                guest=request.guest,
                components=("companions", "ticket"),
                message="L'accompagnant a été retiré.",
            )
        messages.success(request, "L'accompagnant a été retiré.")
    return redirect("guests:rsvp_dashboard")


@require_POST
@guest_access_required
def companion_attendance(request, companion_id):
    companion = get_object_or_404(
        Guest,
        pk=companion_id,
        invitation_owner=request.guest,
        is_active=True,
    )
    form = CompanionAttendanceForm(request.POST, companion=companion)
    if form.is_valid():
        try:
            update_companion_attendance(
                primary_guest=request.guest,
                companion=companion,
                attendance_mode=form.cleaned_data["attendance_mode"],
                event_responses=form.event_responses(),
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            if _is_async_request(request):
                return _fragment_response(
                    request,
                    guest=request.guest,
                    components=("companions",),
                    message="Les disponibilités de l’accompagnant ont été enregistrées.",
                )
            messages.success(request, "Les disponibilités de l’accompagnant ont été enregistrées.")
            return redirect("guests:rsvp_dashboard")
    message = "; ".join(form.non_field_errors()) or "Certaines disponibilités sont invalides."
    if _is_async_request(request):
        return _fragment_response(request, guest=request.guest, components=("companions",), message=message, status=422)
    messages.error(request, message)
    return redirect("guests:rsvp_dashboard")


@require_POST
@guest_access_required
def party_composition_confirm(request):
    was_already_confirmed = request.guest.party_composition_confirmed_at is not None
    try:
        confirmed_guest = confirm_party_composition(
            primary_guest=request.guest,
            come_alone=request.POST.get("come_alone") == "1",
        )
    except ValidationError as exc:
        message = "; ".join(exc.messages)
        status = 422
    else:
        party_label = "personne" if confirmed_guest.confirmed_party_size == 1 else "personnes"
        editable_until = timezone.localtime(
            confirmed_guest.party_composition_editable_until
        ).strftime("%d/%m/%Y à %H:%M")
        if was_already_confirmed:
            message = (
                f"Composition mise à jour : {confirmed_guest.confirmed_party_size} "
                f"{party_label} sur {confirmed_guest.party_size_limit}. "
                f"La date limite reste fixée au {editable_until}."
            )
        else:
            message = (
                f"Composition confirmée : {confirmed_guest.confirmed_party_size} "
                f"{party_label} sur {confirmed_guest.party_size_limit}. "
                f"Modifiable jusqu’au {editable_until}."
            )
        status = 200
    if _is_async_request(request):
        return _fragment_response(
            request,
            guest=request.guest,
            components=("companions", "ticket"),
            message=message,
            status=status,
        )
    messages.success(request, message) if status == 200 else messages.error(request, message)
    return redirect("guests:rsvp_dashboard")


@require_POST
@guest_access_required
def email_update(request):
    if not is_rsvp_open():
        message = "La date limite est dépassée. Contactez-nous pour modifier votre email."
        if _is_async_request(request):
            return _fragment_response(
                request,
                guest=request.guest,
                components=("email",),
                message=message,
                status=422,
            )
        messages.error(request, message)
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
            for error in exc.messages:
                form.add_error(None, error)
        except Exception:
            logger.exception("Impossible d'envoyer la vérification email du guest %s", request.guest.pk)
            if _is_async_request(request):
                return _fragment_response(
                    request,
                    guest=request.guest,
                    components=("email",),
                    message="L'email n'a pas pu être envoyé. Merci de réessayer.",
                    status=502,
                )
            messages.error(request, "L'email n'a pas pu être envoyé. Merci de réessayer.")
            return redirect("guests:rsvp_dashboard")
        else:
            if _is_async_request(request):
                return _fragment_response(
                    request,
                    guest=request.guest,
                    components=("email",),
                    message="Un lien de vérification vient de vous être envoyé.",
                )
            messages.success(request, "Un lien de vérification vient de vous être envoyé.")
            return redirect("guests:rsvp_dashboard")
    if _is_async_request(request):
        return _fragment_response(
            request,
            guest=request.guest,
            components=("email",),
            message="Saisissez une adresse email valide.",
            status=422,
            email_form=form,
        )
    messages.error(request, "; ".join(form.non_field_errors()) or "Saisissez une adresse email valide.")
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


def _ticket_primary(request):
    return Guest.objects.prefetch_related(
        "event_invitations__event",
        "companions",
    ).select_related("ticket").get(pk=request.guest.pk)


def _party_member_or_404(primary_guest, guest_id):
    if guest_id == primary_guest.pk:
        return primary_guest
    return get_object_or_404(
        Guest,
        pk=guest_id,
        invitation_owner=primary_guest,
        is_active=True,
    )


def _ensure_ticket_access(request, primary_guest):
    if party_rsvp_complete(primary_guest):
        return True
    messages.info(request, "Terminez votre RSVP avant d'accéder à vos billets.")
    return False


@guest_access_required
def ticket_preview(request):
    primary_guest = _ticket_primary(request)
    if not _ensure_ticket_access(request, primary_guest):
        return redirect("guests:rsvp_dashboard")

    ticket = getattr(primary_guest, "ticket", None)
    return render(
        request,
        "guests/ticket_preview.html",
        {
            "guest": primary_guest,
            "members": party_members(primary_guest),
            "ticket": ticket,
            "ticket_is_current": bool(
                ticket and ticket_is_current(ticket, primary_guest)
            ),
            "can_email": bool(primary_guest.email and primary_guest.email_verified_at),
        },
    )


@require_POST
@guest_access_required
def ticket_generate(request, guest_id):
    primary_guest = _ticket_primary(request)
    if not _ensure_ticket_access(request, primary_guest):
        return redirect("guests:rsvp_dashboard")
    _party_member_or_404(primary_guest, guest_id)
    try:
        generate_ticket(primary_guest)
    except TicketGenerationError:
        logger.exception("Impossible de générer le billet du groupe %s", primary_guest.pk)
        messages.error(request, "Le billet n'a pas pu être généré. Merci de réessayer.")
    else:
        messages.success(request, "Le billet de votre invitation est prêt.")
    return redirect("guests:ticket_preview")


@require_POST
@guest_access_required
def ticket_generate_all(request):
    primary_guest = _ticket_primary(request)
    if not _ensure_ticket_access(request, primary_guest):
        return redirect("guests:rsvp_dashboard")
    try:
        generate_ticket(primary_guest)
    except TicketGenerationError:
        logger.exception("Impossible de générer le billet du groupe %s", primary_guest.pk)
        messages.error(request, "Le billet de groupe n'a pas pu être généré.")
    else:
        messages.success(request, "Le billet de votre invitation est prêt.")
    return redirect("guests:ticket_preview")


@guest_access_required
def ticket_download(request, guest_id, file_format):
    primary_guest = _ticket_primary(request)
    if not _ensure_ticket_access(request, primary_guest):
        return redirect("guests:rsvp_dashboard")
    _party_member_or_404(primary_guest, guest_id)
    if file_format not in {"jpg", "pdf"}:
        raise Http404
    ticket = getattr(primary_guest, "ticket", None)
    if not ticket or not ticket_is_current(ticket, primary_guest):
        messages.info(request, "Générez ou actualisez d'abord ce billet.")
        return redirect("guests:ticket_preview")

    file_field = ticket.jpg_file if file_format == "jpg" else ticket.pdf_file
    extension = "jpg" if file_format == "jpg" else "pdf"
    file_field.open("rb")
    return FileResponse(
        file_field,
        as_attachment=True,
        filename=f"billet-groupe-{primary_guest.qr_token}.{extension}",
    )


@guest_access_required
def ticket_image(request, guest_id):
    primary_guest = _ticket_primary(request)
    if not _ensure_ticket_access(request, primary_guest):
        return redirect("guests:rsvp_dashboard")
    _party_member_or_404(primary_guest, guest_id)
    ticket = getattr(primary_guest, "ticket", None)
    if not ticket or not ticket_is_current(ticket, primary_guest):
        raise Http404
    ticket.jpg_file.open("rb")
    return FileResponse(ticket.jpg_file, content_type="image/jpeg")


@require_POST
@guest_access_required
def party_ticket_download(request):
    primary_guest = _ticket_primary(request)
    if not _ensure_ticket_access(request, primary_guest):
        return redirect("guests:rsvp_dashboard")
    try:
        content = build_party_pdf(primary_guest)
    except TicketGenerationError:
        messages.error(request, "Le PDF groupé n'a pas pu être préparé.")
        return redirect("guests:ticket_preview")
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="billet-groupe-mariage.pdf"'
    return response


@guest_access_required
def ticket_information_download(request):
    primary_guest = _ticket_primary(request)
    if not _ensure_ticket_access(request, primary_guest):
        return redirect("guests:rsvp_dashboard")
    try:
        content = build_information_jpg()
    except TicketGenerationError:
        logger.exception("Impossible de préparer la page d'informations du billet")
        messages.error(request, "La page d'informations n'a pas pu être préparée.")
        return redirect("guests:ticket_preview")
    response = HttpResponse(content, content_type="image/jpeg")
    response["Content-Disposition"] = (
        'attachment; filename="programme-et-dress-code.jpg"'
    )
    return response


@require_POST
@guest_access_required
def ticket_email(request):
    primary_guest = _ticket_primary(request)
    if not _ensure_ticket_access(request, primary_guest):
        return redirect("guests:rsvp_dashboard")
    if not primary_guest.email or not primary_guest.email_verified_at:
        messages.error(request, "Vérifiez d'abord votre adresse email depuis le RSVP.")
        return redirect("guests:ticket_preview")
    try:
        pdf_content = build_party_pdf(primary_guest)
        send_ticket_email(guest=primary_guest, pdf_content=pdf_content)
    except Exception:
        logger.exception("Impossible d'envoyer les billets du guest %s", primary_guest.pk)
        messages.error(request, "L'email n'a pas pu être envoyé. Merci de réessayer.")
    else:
        messages.success(request, f"Les billets ont été envoyés à {primary_guest.email}.")
    return redirect("guests:ticket_preview")


def public_qr_landing(request, token):
    guest_exists = Guest.objects.filter(qr_token=token, is_active=True).exists()
    return render(request, "guests/public_qr_landing.html", {"recognized": guest_exists})
