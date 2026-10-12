from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render

from guests.models import DinnerTable, DinnerSeatingAssignment
from guests.services.seating import assign_guests, create_table, dinner_guests, exchange_guests, remove_assignment


class SeatingActionForm(forms.Form):
    action = forms.ChoiceField(choices=[(x, x) for x in ("create", "assign", "remove", "exchange")])
    number = forms.IntegerField(min_value=1, max_value=32767, required=False)
    name = forms.CharField(max_length=100, required=False)
    table_id = forms.IntegerField(min_value=1, required=False)
    guest_id = forms.IntegerField(min_value=1, required=False)
    second_id = forms.IntegerField(min_value=1, required=False)

    def clean(self):
        data = super().clean()
        required = {"create": ["number", "name"], "assign": ["table_id"], "remove": ["guest_id"], "exchange": ["guest_id", "second_id"]}
        for key in required.get(data.get("action"), []):
            if not data.get(key):
                self.add_error(key, "Ce champ est requis.")
        return data


def seating_view(model_admin, request):
    if not model_admin.has_view_permission(request):
        raise PermissionDenied
    can_edit = model_admin.has_change_permission(request)
    error = None
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        form = SeatingActionForm(request.POST)
        try:
            if not form.is_valid():
                raise ValidationError([message for errors in form.errors.values() for message in errors])
            data = form.cleaned_data
            if data["action"] == "create":
                create_table(number=data["number"], name=data["name"])
            elif data["action"] == "assign":
                raw_ids = request.POST.getlist("guest_ids")
                if len(raw_ids) > 10 or any(not value.isdecimal() for value in raw_ids):
                    raise ValidationError("Sélectionnez de 1 à 10 invités.")
                assign_guests(guest_ids=[int(value) for value in raw_ids], table_id=data["table_id"])
            elif data["action"] == "remove":
                remove_assignment(guest_id=data["guest_id"])
            else:
                exchange_guests(first_id=data["guest_id"], second_id=data["second_id"])
        except ValidationError as exc:
            error = " ".join(exc.messages)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"error": error}, status=400 if error else 200)
        if not error:
            return redirect("admin:guests_guest_seating")
    guests = list(dinner_guests())
    confirmed_ids = {guest.pk for guest in guests}
    assignments = list(DinnerSeatingAssignment.objects.select_related("guest", "guest__invitation_owner", "table"))
    assigned_ids = {item.guest_id for item in assignments}
    tables = list(DinnerTable.objects.all())
    for table in tables:
        table.rows = [item for item in assignments if item.table_id == table.pk]
        for item in table.rows:
            item.is_anomaly = item.guest_id not in confirmed_ids
        table.remaining = table.capacity - len(table.rows)
    return render(request, "admin/guests/guest/seating.html", {
        **model_admin.admin_site.each_context(request), "opts": model_admin.model._meta,
        "title": "Plan de tables — Dîner", "tables": tables, "can_edit": can_edit,
        "unassigned": [guest for guest in guests if guest.pk not in assigned_ids],
        "placed": [item for item in assignments if item.guest_id in confirmed_ids],
        "confirmed_count": len(guests), "placed_count": len(confirmed_ids & assigned_ids),
        "unassigned_count": len(confirmed_ids - assigned_ids),
        "anomaly_count": len(assigned_ids - confirmed_ids), "error": error,
    })


def seating_export_view(model_admin, request):
    from django.http import HttpResponse, HttpResponseBadRequest
    from guests.services.seating_export import build_seating_pdf

    if not model_admin.has_view_permission(request):
        raise PermissionDenied
    if request.method != "GET":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["GET"])
    layout = request.GET.get("layout", "summary")
    if layout not in {"summary", "tables"}:
        return HttpResponseBadRequest("Format d’export inconnu.")
    response = HttpResponse(build_seating_pdf(per_table=layout == "tables"), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="plan-tables-diner-{layout}.pdf"'
    response["Cache-Control"] = "private, no-store"
    return response
