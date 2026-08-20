from django.db import migrations


def backfill_guest_type(apps, schema_editor):
    Guest = apps.get_model("guests", "Guest")
    SpecialDemand = apps.get_model("specialdemands", "SpecialDemand")

    accepted = SpecialDemand.objects.filter(status="accepted")
    witness_ids = accepted.filter(demand_type="witness").values_list("guest_id", flat=True)
    honor_ids = accepted.filter(demand_type__in=["maid_of_honor", "best_man"]).values_list("guest_id", flat=True)

    Guest.objects.filter(pk__in=honor_ids).update(guest_type="honor")
    Guest.objects.filter(pk__in=witness_ids).update(guest_type="witness")
    Guest.objects.filter(guest_type__isnull=True, is_vip=False).update(guest_type="regular")


def reverse_backfill(apps, schema_editor):
    Guest = apps.get_model("guests", "Guest")
    Guest.objects.update(guest_type=None)


class Migration(migrations.Migration):
    dependencies = [
        ("guests", "0002_guest_workflow_fields"),
        ("specialdemands", "0003_alter_specialdemand_notify_emails"),
    ]

    operations = [
        migrations.RunPython(backfill_guest_type, reverse_backfill),
    ]
