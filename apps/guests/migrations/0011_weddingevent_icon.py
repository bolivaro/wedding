from django.db import migrations, models


def populate_event_icons(apps, schema_editor):
    WeddingEvent = apps.get_model("guests", "WeddingEvent")
    icons = {
        "city_hall": "city_hall",
        "church": "church",
        "cocktail": "toast",
        "reception": "dinner",
    }
    for code, icon in icons.items():
        WeddingEvent.objects.filter(code=code).update(icon=icon)


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0010_weddingevent_location_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="weddingevent",
            name="icon",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Aucun pictogramme"),
                    ("city_hall", "Mairie / édifice civil"),
                    ("church", "Église"),
                    ("toast", "Vin d'honneur / flûtes"),
                    ("dinner", "Repas / dîner"),
                    ("party", "Soirée dansante"),
                ],
                max_length=20,
                verbose_name="pictogramme",
            ),
        ),
        migrations.RunPython(populate_event_icons, migrations.RunPython.noop),
    ]
