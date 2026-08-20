import guests.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0007_case_insensitive_guest_email"),
    ]

    operations = [
        migrations.CreateModel(
            name="Ticket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "À générer"), ("ready", "Prêt"), ("failed", "Échec")], default="pending", max_length=20, verbose_name="statut")),
                ("jpg_file", models.FileField(blank=True, upload_to=guests.models.guest_ticket_upload_to, verbose_name="billet JPG")),
                ("pdf_file", models.FileField(blank=True, upload_to=guests.models.guest_ticket_upload_to, verbose_name="billet PDF")),
                ("template_version", models.CharField(blank=True, max_length=100, verbose_name="version du gabarit")),
                ("template_checksum", models.CharField(blank=True, max_length=64, verbose_name="empreinte du gabarit")),
                ("render_signature", models.CharField(blank=True, max_length=64, verbose_name="empreinte du rendu")),
                ("generated_at", models.DateTimeField(blank=True, null=True, verbose_name="généré le")),
                ("last_error", models.TextField(blank=True, verbose_name="dernière erreur")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="mis à jour le")),
                ("guest", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="ticket", to="guests.guest", verbose_name="invité")),
            ],
            options={
                "verbose_name": "billet",
                "verbose_name_plural": "billets",
                "ordering": ["guest__first_name", "guest__last_name"],
            },
        ),
    ]
