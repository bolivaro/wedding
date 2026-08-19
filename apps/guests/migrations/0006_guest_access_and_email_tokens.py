import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0005_guest_import_models"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GuestAccessCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("selector", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="sélecteur")),
                ("secret_hash", models.CharField(editable=False, max_length=255, verbose_name="empreinte du secret")),
                ("expires_at", models.DateTimeField(verbose_name="expire le")),
                ("revoked_at", models.DateTimeField(blank=True, null=True, verbose_name="révoqué le")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="créé le")),
                ("last_used_at", models.DateTimeField(blank=True, null=True, verbose_name="dernière utilisation")),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0, verbose_name="tentatives échouées")),
                ("locked_until", models.DateTimeField(blank=True, null=True, verbose_name="verrouillé jusqu'au")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_guest_credentials", to=settings.AUTH_USER_MODEL, verbose_name="créé par")),
                ("guest", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="access_credentials", to="guests.guest", verbose_name="invité")),
            ],
            options={"verbose_name": "accès RSVP", "verbose_name_plural": "accès RSVP", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GuestEmailToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("purpose", models.CharField(choices=[("verify", "Vérification d'email"), ("recover", "Récupération d'accès")], max_length=20, verbose_name="usage")),
                ("selector", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="sélecteur")),
                ("secret_hash", models.CharField(editable=False, max_length=255, verbose_name="empreinte du secret")),
                ("target_email", models.EmailField(max_length=254, verbose_name="adresse concernée")),
                ("expires_at", models.DateTimeField(verbose_name="expire le")),
                ("used_at", models.DateTimeField(blank=True, null=True, verbose_name="utilisé le")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="créé le")),
                ("guest", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="email_tokens", to="guests.guest", verbose_name="invité")),
            ],
            options={"verbose_name": "jeton email invité", "verbose_name_plural": "jetons email invités", "ordering": ["-created_at"]},
        ),
    ]
