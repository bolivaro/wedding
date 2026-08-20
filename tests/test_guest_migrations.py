from zoneinfo import ZoneInfo

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class CocktailEventMigrationTests(TransactionTestCase):
    migrate_from = [("guests", "0008_ticket")]
    migrate_to = [("guests", "0009_weddingevent_cocktail_and_requires_rsvp")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Guest = old_apps.get_model("guests", "Guest")
        GuestEventInvitation = old_apps.get_model("guests", "GuestEventInvitation")
        WeddingEvent = old_apps.get_model("guests", "WeddingEvent")
        guest = Guest.objects.create(first_name="Marie")
        church = WeddingEvent.objects.get(code="church")
        GuestEventInvitation.objects.create(
            guest=guest,
            event=church,
            is_eligible=True,
            attendance_status="attending",
            response_source="admin",
        )
        self.guest_id = guest.pk

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_cocktail_is_created_without_losing_existing_rsvp_data(self):
        GuestEventInvitation = self.apps.get_model("guests", "GuestEventInvitation")
        WeddingEvent = self.apps.get_model("guests", "WeddingEvent")

        cocktail = WeddingEvent.objects.get(code="cocktail")
        reception = WeddingEvent.objects.get(code="reception")
        mirrored = GuestEventInvitation.objects.get(
            guest_id=self.guest_id,
            event=cocktail,
        )

        self.assertEqual(cocktail.name, "Vin d'honneur")
        self.assertEqual(
            timezone.localtime(cocktail.starts_at, ZoneInfo("Europe/Paris")).hour,
            14,
        )
        self.assertEqual(cocktail.display_order, 30)
        self.assertFalse(cocktail.requires_rsvp)
        self.assertEqual(reception.display_order, 40)
        self.assertTrue(mirrored.is_eligible)
        self.assertEqual(mirrored.attendance_status, "attending")
        self.assertEqual(mirrored.response_source, "admin")
