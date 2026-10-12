from django.db import migrations
from django.db.models import Max


TABLE_NAMES = (
    "Balepouo",
    "Bamelieu",
    "Bassessa Fotsa",
    "Keleng",
    "Leffe",
    "Metsi",
    "Mezet",
    "Ndoh-Djuttitsa",
    "Nzemla",
    "Tsingbeu",
    "Ziefeng",
    "Zemtsuet 1",
    "Song Njouma",
    "Song Kwalla",
    "Somakek",
    "Kopongo",
    "Bessombe",
    "Song Loulou",
    "Bossèdi I",
    "Biendèndè",
    "Bonatakwa",
    "Bonamoulèndè",
    "Yamitèki",
    "Bona Ataka",
    "Etoug-ebe",
    "Bessengue",
)


def create_default_tables(apps, schema_editor):
    DinnerTable = apps.get_model("guests", "DinnerTable")
    tables = DinnerTable.objects.using(schema_editor.connection.alias)
    existing_names = {name.strip().casefold() for name in tables.values_list("name", flat=True)}
    number = tables.aggregate(last=Max("number"))["last"] or 0
    for name in TABLE_NAMES:
        if name.casefold() not in existing_names:
            number += 1
            tables.create(name=name, number=number)
            existing_names.add(name.casefold())


class Migration(migrations.Migration):
    dependencies = [("guests", "0019_alter_dinnertable_options")]
    operations = [migrations.RunPython(create_default_tables, migrations.RunPython.noop)]
