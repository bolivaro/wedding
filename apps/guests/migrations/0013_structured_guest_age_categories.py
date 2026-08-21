from django.db import migrations, models


AGE_CATEGORY_MAPPING = {
    "Bébé (0–2)": "baby_0_2",
    "Bébé (0–2 ans)": "baby_0_2",
    "Enfant (3–12)": "child_3_12",
    "Enfant (3–12 ans)": "child_3_12",
    "Adolescent (13–17)": "teenager_13_17",
    "Adolescent (13–17 ans)": "teenager_13_17",
    "Adulte (18–44)": "adult_18_44",
    "Adulte (18–44 ans)": "adult_18_44",
    "adult_18_plus": "adult_18_44",
    "Adulte confirmé (45–59)": "adult_45_59",
    "Adulte confirmé (45–59 ans)": "adult_45_59",
    "Senior (60+)": "senior_60_plus",
    "Senior (60 ans et plus)": "senior_60_plus",
}


def normalize_age_categories(apps, schema_editor):
    Guest = apps.get_model("guests", "Guest")
    for source_value, target_value in AGE_CATEGORY_MAPPING.items():
        Guest.objects.filter(age_category=source_value).update(age_category=target_value)


class Migration(migrations.Migration):
    dependencies = [("guests", "0012_weddingevent_description")]

    operations = [
        migrations.RunPython(normalize_age_categories, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="guest",
            name="age_category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("baby_0_2", "Bébé (0–2)"),
                    ("child_3_12", "Enfant (3–12)"),
                    ("teenager_13_17", "Adolescent (13–17)"),
                    ("adult_18_44", "Adulte (18–44)"),
                    ("adult_45_59", "Adulte confirmé (45–59)"),
                    ("senior_60_plus", "Senior (60+)"),
                ],
                max_length=50,
                verbose_name="catégorie d'âge",
            ),
        ),
    ]
