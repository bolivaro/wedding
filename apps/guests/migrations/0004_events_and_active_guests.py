import django.db.models.deletion
from django.db import migrations, models


def create_wedding_events(apps, schema_editor):
    WeddingEvent = apps.get_model("guests", "WeddingEvent")
    for code, name, order in [
        ("city_hall", "Mairie", 10),
        ("church", "Église", 20),
        ("reception", "Soirée", 30),
    ]:
        WeddingEvent.objects.get_or_create(code=code, defaults={"name": name, "display_order": order})


def remove_wedding_events(apps, schema_editor):
    WeddingEvent = apps.get_model("guests", "WeddingEvent")
    WeddingEvent.objects.filter(code__in=["city_hall", "church", "reception"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0003_backfill_guest_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="guest",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="actif"),
        ),
        migrations.CreateModel(
            name="WeddingEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(choices=[("city_hall", "Mairie"), ("church", "Église"), ("reception", "Soirée")], max_length=30, unique=True, verbose_name="code")),
                ("name", models.CharField(max_length=100, verbose_name="nom")),
                ("starts_at", models.DateTimeField(blank=True, null=True, verbose_name="début")),
                ("capacity", models.PositiveIntegerField(blank=True, null=True, verbose_name="capacité")),
                ("display_order", models.PositiveSmallIntegerField(default=0, verbose_name="ordre")),
                ("is_active", models.BooleanField(default=True, verbose_name="actif")),
            ],
            options={"verbose_name": "événement du mariage", "verbose_name_plural": "événements du mariage", "ordering": ["display_order", "name"]},
        ),
        migrations.CreateModel(
            name="GuestEventInvitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_eligible", models.BooleanField(default=True, verbose_name="éligible")),
                ("attendance_status", models.CharField(choices=[("pending", "En attente"), ("attending", "Présent"), ("not_attending", "Absent")], default="pending", max_length=20, verbose_name="présence")),
                ("response_source", models.CharField(blank=True, choices=[("excel", "Import Excel"), ("guest", "Invité"), ("admin", "Administration")], max_length=20, verbose_name="source de la réponse")),
                ("responded_at", models.DateTimeField(blank=True, null=True, verbose_name="répondu le")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="guest_invitations", to="guests.weddingevent", verbose_name="événement")),
                ("guest", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="event_invitations", to="guests.guest", verbose_name="invité")),
            ],
            options={"verbose_name": "invitation à un événement", "verbose_name_plural": "invitations aux événements", "ordering": ["event__display_order"]},
        ),
        migrations.AddConstraint(
            model_name="guesteventinvitation",
            constraint=models.UniqueConstraint(fields=("guest", "event"), name="unique_guest_event_invitation"),
        ),
        migrations.AddConstraint(
            model_name="guesteventinvitation",
            constraint=models.CheckConstraint(condition=models.Q(("is_eligible", True), models.Q(("attendance_status", "attending"), _negated=True), _connector="OR"), name="ineligible_guest_cannot_attend_event"),
        ),
        migrations.RunPython(create_wedding_events, remove_wedding_events),
    ]
