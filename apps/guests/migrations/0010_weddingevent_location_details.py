from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import migrations, models


PUTEAUX_TOWN_HALL_MAP = (
    "https://www.google.com/maps/place//data=!4m2!3m1!"
    "1s0x47e6651ba5f444f3:0xaccade36aa0a4e12?sa=X&ved=1t:8290&ictx=111"
)
SAINTE_MATHILDE_MAP = (
    "https://www.google.com/maps/place//data=!4m2!3m1!"
    "1s0x47e6651e87bdce9f:0x9c5cfb245d6eaff7?sa=X&ved=1t:8290&ictx=111"
)
PALAIS_GROUPE_91_MAP = (
    "https://www.google.com/maps/place//data=!4m2!3m1!"
    "1s0x47e5de66169627d9:0xf41889fce0dc6db8?sa=X&ved=1t:8290&ictx=111"
)


def populate_event_details(apps, schema_editor):
    WeddingEvent = apps.get_model("guests", "WeddingEvent")
    paris = ZoneInfo("Europe/Paris")
    details = {
        "city_hall": {
            "name": "Cérémonie civile",
            "venue_name": "Mairie de Puteaux",
            "address": "131 Rue de la République, 92800 Puteaux",
            "map_url": PUTEAUX_TOWN_HALL_MAP,
            "starts_at": datetime(2026, 10, 17, 10, 30, tzinfo=paris),
        },
        "church": {
            "name": "Cérémonie religieuse",
            "venue_name": "Église Sainte-Mathilde",
            "address": "33 Rue Lucien Voilin, 92800 Puteaux",
            "map_url": SAINTE_MATHILDE_MAP,
            "starts_at": datetime(2026, 10, 17, 12, 30, tzinfo=paris),
        },
        "cocktail": {
            "name": "Vin d'honneur",
            "venue_name": "Salle des Cailloux, Église Sainte-Mathilde",
            "address": "33 Rue Lucien Voilin, 92800 Puteaux",
            "map_url": SAINTE_MATHILDE_MAP,
            "starts_at": datetime(2026, 10, 17, 14, 0, tzinfo=paris),
        },
        "reception": {
            "name": "Dîner",
            "venue_name": "Palais Groupe 91",
            "address": "2 Rue Jules Guesde, 91130 Ris-Orangis",
            "map_url": PALAIS_GROUPE_91_MAP,
            "starts_at": datetime(2026, 10, 17, 19, 30, tzinfo=paris),
        },
    }
    for code, values in details.items():
        WeddingEvent.objects.filter(code=code).update(**values)


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0009_weddingevent_cocktail_and_requires_rsvp"),
    ]

    operations = [
        migrations.AddField(
            model_name="weddingevent",
            name="address",
            field=models.CharField(blank=True, max_length=255, verbose_name="adresse"),
        ),
        migrations.AddField(
            model_name="weddingevent",
            name="map_url",
            field=models.URLField(
                blank=True,
                max_length=1000,
                verbose_name="lien cartographique",
            ),
        ),
        migrations.AddField(
            model_name="weddingevent",
            name="venue_name",
            field=models.CharField(blank=True, max_length=200, verbose_name="lieu"),
        ),
        migrations.RunPython(populate_event_details, migrations.RunPython.noop),
    ]
