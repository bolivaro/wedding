from django.db import migrations, models
from django.db.models.functions import Lower


def normalize_guest_emails(apps, schema_editor):
    Guest = apps.get_model("guests", "Guest")
    normalized_to_ids = {}
    updates = []
    for guest in Guest.objects.exclude(email__isnull=True).only("pk", "email"):
        normalized = guest.email.strip().casefold()
        if not normalized:
            normalized = None
        if normalized:
            normalized_to_ids.setdefault(normalized, []).append(guest.pk)
        updates.append((guest, normalized))

    collisions = {
        email: ids for email, ids in normalized_to_ids.items() if len(ids) > 1
    }
    if collisions:
        conflicting_ids = sorted(
            guest_id for ids in collisions.values() for guest_id in ids
        )
        raise RuntimeError(
            "Des emails invités sont identiques après normalisation. "
            f"Résoudre les Guest IDs suivants avant migration : {conflicting_ids}"
        )

    for guest, normalized in updates:
        if guest.email != normalized:
            guest.email = normalized
            guest.save(update_fields=["email"])


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0006_guest_access_and_email_tokens"),
    ]

    operations = [
        migrations.RunPython(normalize_guest_emails, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="guest",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True, verbose_name="email"),
        ),
        migrations.AddConstraint(
            model_name="guest",
            constraint=models.UniqueConstraint(
                Lower("email"),
                condition=models.Q(("email__isnull", False)),
                name="unique_guest_email_case_insensitive",
            ),
        ),
    ]
