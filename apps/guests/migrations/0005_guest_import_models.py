import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import guests.models


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0004_events_and_active_guests"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GuestImportBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to=guests.models.guest_import_upload_to, verbose_name="fichier Excel")),
                ("original_filename", models.CharField(max_length=255, verbose_name="nom du fichier")),
                ("checksum", models.CharField(max_length=64, unique=True, verbose_name="empreinte SHA-256")),
                ("status", models.CharField(choices=[("uploaded", "Téléversé"), ("analyzed", "Analysé"), ("applied", "Appliqué"), ("failed", "Échec")], default="uploaded", max_length=20, verbose_name="statut")),
                ("summary", models.JSONField(blank=True, default=dict, verbose_name="résumé")),
                ("error_message", models.TextField(blank=True, verbose_name="erreur")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="créé le")),
                ("applied_at", models.DateTimeField(blank=True, null=True, verbose_name="appliqué le")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="guest_import_batches", to=settings.AUTH_USER_MODEL, verbose_name="créé par")),
            ],
            options={"verbose_name": "import d'invités", "verbose_name_plural": "imports d'invités", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GuestImportRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sheet_name", models.CharField(max_length=100, verbose_name="feuille")),
                ("row_number", models.PositiveIntegerField(verbose_name="numéro de ligne")),
                ("source_key", models.CharField(blank=True, max_length=255, verbose_name="clé source")),
                ("raw_data", models.JSONField(default=dict, verbose_name="données source")),
                ("outcome", models.CharField(choices=[("new", "Nouvel invité"), ("matched", "Invité existant"), ("ambiguous", "Correspondance ambiguë"), ("conflict", "Conflit"), ("invalid", "Ligne invalide")], max_length=20, verbose_name="résultat")),
                ("proposed_changes", models.JSONField(blank=True, default=dict, verbose_name="modifications proposées")),
                ("messages", models.JSONField(blank=True, default=list, verbose_name="messages")),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rows", to="guests.guestimportbatch", verbose_name="import")),
                ("matched_guest", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="import_rows", to="guests.guest", verbose_name="invité trouvé")),
            ],
            options={"verbose_name": "ligne d'import", "verbose_name_plural": "lignes d'import", "ordering": ["sheet_name", "row_number"]},
        ),
        migrations.CreateModel(
            name="GuestSourceRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(default="excel", max_length=30, verbose_name="source")),
                ("external_key", models.CharField(max_length=255, verbose_name="clé externe")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="mis à jour le")),
                ("guest", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="source_records", to="guests.guest", verbose_name="invité")),
                ("last_seen_batch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="source_records", to="guests.guestimportbatch", verbose_name="dernier import")),
            ],
            options={"verbose_name": "identité source d'un invité", "verbose_name_plural": "identités source des invités"},
        ),
        migrations.AddConstraint(model_name="guestimportrow", constraint=models.UniqueConstraint(fields=("batch", "sheet_name", "row_number"), name="unique_row_per_guest_import")),
        migrations.AddConstraint(model_name="guestsourcerecord", constraint=models.UniqueConstraint(fields=("source", "external_key"), name="unique_guest_external_source_key")),
    ]
