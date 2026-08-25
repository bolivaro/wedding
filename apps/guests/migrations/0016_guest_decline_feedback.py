from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("guests", "0015_guesteventinvitation_eligibility_source")]

    operations = [
        migrations.AddField(
            model_name="guest",
            name="decline_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("unavailable", "Indisponible à cette date"),
                    ("travel", "Distance ou déplacement"),
                    ("personal", "Raison personnelle ou familiale"),
                    ("health", "Raison de santé"),
                    ("other_commitment", "Autre engagement"),
                    ("other", "Autre raison"),
                    ("prefer_not_to_say", "Je préfère ne pas préciser"),
                ],
                max_length=30,
                verbose_name="motif du refus",
            ),
        ),
        migrations.AddField(
            model_name="guest",
            name="decline_message",
            field=models.TextField(
                blank=True,
                max_length=1000,
                verbose_name="message associé au refus",
            ),
        ),
    ]
