import uuid

import django.db.models.deletion
from django.db import migrations, models


def populate_unique_qr_tokens(apps, schema_editor):
    Guest = apps.get_model("guests", "Guest")
    for guest in Guest.objects.filter(qr_token__isnull=True).iterator():
        guest.qr_token = uuid.uuid4()
        guest.save(update_fields=["qr_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="guest",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True, unique=True, verbose_name="email"),
        ),
        migrations.AddField(
            model_name="guest",
            name="pending_email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="nouvel email à vérifier"),
        ),
        migrations.AddField(
            model_name="guest",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="email vérifié le"),
        ),
        migrations.AddField(
            model_name="guest",
            name="guest_type",
            field=models.CharField(blank=True, choices=[("regular", "Invité classique"), ("honor", "Personne d'honneur"), ("witness", "Témoin"), ("parent", "Parent")], max_length=20, null=True, verbose_name="type d'invité"),
        ),
        migrations.AddField(
            model_name="guest",
            name="gender",
            field=models.CharField(choices=[("male", "Homme"), ("female", "Femme"), ("other", "Autre"), ("unspecified", "Non renseigné")], default="unspecified", max_length=20, verbose_name="genre"),
        ),
        migrations.AddField(
            model_name="guest",
            name="guest_group",
            field=models.CharField(blank=True, choices=[("bride_family", "Famille femme"), ("groom_family", "Famille mari"), ("bride_friends", "Amis femme"), ("groom_friends", "Amis mari")], max_length=30, verbose_name="groupe d'invités"),
        ),
        migrations.AddField(
            model_name="guest",
            name="invitation_kind",
            field=models.CharField(choices=[("single", "Individuelle"), ("couple", "Couple"), ("family", "Famille")], default="single", max_length=20, verbose_name="nature de l'invitation"),
        ),
        migrations.AddField(
            model_name="guest",
            name="party_size_limit",
            field=models.PositiveSmallIntegerField(default=1, help_text="Inclut l'invité principal.", verbose_name="nombre total de places autorisées"),
        ),
        migrations.AddField(
            model_name="guest",
            name="invitation_owner",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="companions", to="guests.guest", verbose_name="invité principal"),
        ),
        migrations.AddField(model_name="guest", name="has_been_contacted", field=models.BooleanField(blank=True, null=True, verbose_name="contacté")),
        migrations.AddField(model_name="guest", name="requires_visa", field=models.BooleanField(blank=True, null=True, verbose_name="soumis au visa")),
        migrations.AddField(model_name="guest", name="age_category", field=models.CharField(blank=True, max_length=50, verbose_name="catégorie d'âge")),
        migrations.AddField(model_name="guest", name="origin_country", field=models.CharField(blank=True, max_length=100, verbose_name="origine")),
        migrations.AddField(model_name="guest", name="travel_origin_country", field=models.CharField(blank=True, max_length=100, verbose_name="provenance")),
        migrations.AddField(
            model_name="guest",
            name="rsvp_status",
            field=models.CharField(choices=[("pending", "En attente"), ("attending", "Présent"), ("not_attending", "Absent")], default="pending", max_length=20, verbose_name="statut RSVP"),
        ),
        migrations.AddField(
            model_name="guest",
            name="rsvp_source",
            field=models.CharField(blank=True, choices=[("excel", "Import Excel"), ("guest", "Invité"), ("admin", "Administration")], max_length=20, verbose_name="source du RSVP"),
        ),
        migrations.AddField(model_name="guest", name="rsvp_responded_at", field=models.DateTimeField(blank=True, null=True, verbose_name="RSVP répondu le")),
        migrations.AddField(
            model_name="guest",
            name="qr_token",
            field=models.UUIDField(blank=True, editable=False, null=True, verbose_name="identifiant QR permanent"),
        ),
        migrations.RunPython(
            populate_unique_qr_tokens,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="guest",
            name="qr_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="identifiant QR permanent"),
        ),
        migrations.AddConstraint(
            model_name="guest",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("invitation_kind", "single"), ("party_size_limit", 1))
                    | models.Q(("invitation_kind", "couple"), ("party_size_limit", 2))
                    | models.Q(("invitation_kind", "family"), ("party_size_limit__gte", 2))
                ),
                name="guest_valid_party_size_for_kind",
            ),
        ),
    ]
