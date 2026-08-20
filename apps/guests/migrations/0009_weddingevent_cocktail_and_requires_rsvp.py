from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations, models


def add_cocktail_event(apps, schema_editor):
    GuestEventInvitation = apps.get_model("guests", "GuestEventInvitation")
    WeddingEvent = apps.get_model("guests", "WeddingEvent")

    cocktail, _ = WeddingEvent.objects.update_or_create(
        code="cocktail",
        defaults={
            "name": "Vin d'honneur",
            "starts_at": datetime(2026, 10, 17, 14, 0, tzinfo=ZoneInfo("Europe/Paris")),
            "display_order": 30,
            "is_active": True,
            "requires_rsvp": False,
        },
    )
    WeddingEvent.objects.filter(code="reception").update(display_order=40)

    church_invitations = GuestEventInvitation.objects.filter(
        event__code="church"
    ).iterator()
    for church_invitation in church_invitations:
        GuestEventInvitation.objects.get_or_create(
            guest_id=church_invitation.guest_id,
            event=cocktail,
            defaults={
                "is_eligible": church_invitation.is_eligible,
                "attendance_status": church_invitation.attendance_status,
                "response_source": church_invitation.response_source,
                "responded_at": church_invitation.responded_at,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0008_ticket"),
    ]

    operations = [
        migrations.AddField(
            model_name="weddingevent",
            name="requires_rsvp",
            field=models.BooleanField(
                default=True,
                help_text="Décochez pour afficher l'événement au programme sans question RSVP.",
                verbose_name="demande une réponse RSVP",
            ),
        ),
        migrations.AlterField(
            model_name="weddingevent",
            name="code",
            field=models.CharField(
                choices=[
                    ("city_hall", "Mairie"),
                    ("church", "Église"),
                    ("cocktail", "Vin d'honneur"),
                    ("reception", "Soirée"),
                ],
                max_length=30,
                unique=True,
                verbose_name="code",
            ),
        ),
        migrations.RunPython(add_cocktail_event, migrations.RunPython.noop),
    ]
