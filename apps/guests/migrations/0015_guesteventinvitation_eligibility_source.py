from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("guests", "0014_guest_composition_capacity_and_attendance")]

    operations = [
        migrations.AddField(
            model_name="guesteventinvitation",
            name="eligibility_source",
            field=models.CharField(
                choices=[
                    ("legacy", "Donnée existante"),
                    ("policy", "Règle automatique"),
                    ("import", "Import"),
                    ("admin", "Administration"),
                ],
                default="legacy",
                max_length=20,
                verbose_name="origine de l’éligibilité",
            ),
        ),
    ]
