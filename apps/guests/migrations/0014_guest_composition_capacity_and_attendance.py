from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations, models


EVENT_CAPACITIES = {
    "city_hall": 175,
    "church": 300,
    "cocktail": 300,
    "reception": 280,
}


def configure_events(apps, schema_editor):
    WeddingEvent = apps.get_model("guests", "WeddingEvent")
    deadline = datetime(2026, 10, 16, 23, 59, 59, tzinfo=ZoneInfo("Europe/Paris"))
    for code, capacity in EVENT_CAPACITIES.items():
        updates = {
            "capacity": capacity,
            "attendance_change_deadline": deadline,
        }
        if code == "cocktail":
            updates["requires_rsvp"] = True
        WeddingEvent.objects.filter(code=code).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("guests", "0013_structured_guest_age_categories")]

    operations = [
        migrations.AddField(
            model_name="guest",
            name="attendance_mode",
            field=models.CharField(
                choices=[
                    ("inherit", "Mêmes disponibilités que l’invité principal"),
                    ("custom", "Disponibilités personnalisées"),
                ],
                default="inherit",
                max_length=20,
                verbose_name="mode de disponibilités",
            ),
        ),
        migrations.AddField(model_name="guest", name="confirmed_party_size", field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="taille du groupe confirmée")),
        migrations.AddField(model_name="guest", name="party_composition_confirmed_at", field=models.DateTimeField(blank=True, null=True, verbose_name="composition confirmée le")),
        migrations.AddField(model_name="guest", name="party_composition_editable_until", field=models.DateTimeField(blank=True, null=True, verbose_name="composition modifiable jusqu’au")),
        migrations.AddField(model_name="weddingevent", name="attendance_change_deadline", field=models.DateTimeField(blank=True, null=True, verbose_name="disponibilités modifiables jusqu’au")),
        migrations.RunPython(configure_events, migrations.RunPython.noop),
    ]
