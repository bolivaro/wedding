from django.db import migrations, models


DESCRIPTIONS = {
    "city_hall": "Le début officiel de notre journée, entourés de nos proches.",
    "church": "Un temps de célébration et de partage au cœur de Puteaux.",
    "cocktail": "Retrouvons-nous autour d'un verre avant de poursuivre les festivités.",
    "reception": "Dîner, surprises et soirée dansante pour célébrer ensemble.",
}


def populate_descriptions(apps, schema_editor):
    WeddingEvent = apps.get_model("guests", "WeddingEvent")
    for code, description in DESCRIPTIONS.items():
        WeddingEvent.objects.filter(code=code, description="").update(description=description)


class Migration(migrations.Migration):
    dependencies = [("guests", "0011_weddingevent_icon")]

    operations = [
        migrations.AddField(
            model_name="weddingevent",
            name="description",
            field=models.TextField(blank=True, max_length=500, verbose_name="description courte"),
        ),
        migrations.RunPython(populate_descriptions, migrations.RunPython.noop),
    ]
