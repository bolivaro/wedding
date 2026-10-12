"""Dinner-only seating. All writes serialize on the reception event."""
from django.core.exceptions import ValidationError
from django.db import transaction

from guests.models import DinnerTable, DinnerSeatingAssignment, Guest, WeddingEvent
from guests.services.attendance import present_responses


def dinner_guests():
    return Guest.objects.filter(pk__in=present_responses().filter(
        event__code=WeddingEvent.Code.RECEPTION, event__is_active=True,
    ).values("guest_id")).select_related("invitation_owner").order_by("last_name", "first_name", "pk")


def lock_dinner():
    event = WeddingEvent.objects.select_for_update().filter(code=WeddingEvent.Code.RECEPTION, is_active=True).first()
    if event is None:
        raise ValidationError("L’événement Dîner/Réception est indisponible.")
    return event


@transaction.atomic
def create_table(*, name):
    lock_dinner()
    # Retain the legacy column without exposing numbering to planners.
    from django.db.models import Max
    number = (DinnerTable.objects.aggregate(last=Max("number"))["last"] or 0) + 1
    table = DinnerTable(number=number, name=name.strip())
    table.full_clean()
    table.save()
    return table


@transaction.atomic
def assign_guests(*, guest_ids, table_id):
    lock_dinner()
    ids = set(guest_ids)
    if not ids:
        raise ValidationError("Sélectionnez au moins un invité.")
    # Lock guest rows too, so a simultaneous RSVP cannot change mid-assignment.
    list(Guest.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    if set(dinner_guests().filter(pk__in=ids).values_list("pk", flat=True)) != ids:
        raise ValidationError("Seuls les invités confirmés au dîner peuvent être affectés.")
    table = DinnerTable.objects.filter(pk=table_id).first()
    if table is None:
        raise ValidationError("Cette table n’existe plus.")
    occupied = table.assignments.exclude(guest_id__in=ids).count()
    if occupied + len(ids) > table.capacity:
        raise ValidationError(f"{table} : seulement {table.capacity - occupied} place(s) disponible(s).")
    for guest_id in sorted(ids):
        DinnerSeatingAssignment.objects.update_or_create(guest_id=guest_id, defaults={"table": table})


@transaction.atomic
def remove_assignment(*, guest_id):
    lock_dinner()
    DinnerSeatingAssignment.objects.filter(guest_id=guest_id).delete()


@transaction.atomic
def exchange_guests(*, first_id, second_id):
    lock_dinner()
    ids = {first_id, second_id}
    list(Guest.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(ids) != 2 or set(dinner_guests().filter(pk__in=ids).values_list("pk", flat=True)) != ids:
        raise ValidationError("Sélectionnez deux convives confirmés au dîner.")
    assignments = list(DinnerSeatingAssignment.objects.filter(guest_id__in=ids).order_by("guest_id"))
    if len(assignments) != 2 or assignments[0].table_id == assignments[1].table_id:
        raise ValidationError("Choisissez deux convives placés à des tables différentes.")
    assignments[0].table_id, assignments[1].table_id = assignments[1].table_id, assignments[0].table_id
    for assignment in assignments:
        assignment.save(update_fields=["table", "updated_at"])
