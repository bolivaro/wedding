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


class WeddingEventDetailsMigrationTests(TransactionTestCase):
    migrate_from = [("guests", "0009_weddingevent_cocktail_and_requires_rsvp")]
    migrate_to = [("guests", "0010_weddingevent_location_details")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        WeddingEvent = old_apps.get_model("guests", "WeddingEvent")
        for code, name, display_order in (
            ("city_hall", "Mairie", 10),
            ("church", "Église", 20),
            ("cocktail", "Vin d'honneur", 30),
            ("reception", "Soirée", 40),
        ):
            WeddingEvent.objects.get_or_create(
                code=code,
                defaults={"name": name, "display_order": display_order},
            )
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_all_program_details_are_populated_and_editable(self):
        WeddingEvent = self.apps.get_model("guests", "WeddingEvent")
        expected = {
            "city_hall": (
                "Cérémonie civile",
                "Mairie de Puteaux",
                "131 Rue de la République, 92800 Puteaux",
                10,
                30,
            ),
            "church": (
                "Cérémonie religieuse",
                "Église Sainte-Mathilde",
                "33 Rue Lucien Voilin, 92800 Puteaux",
                12,
                30,
            ),
            "cocktail": (
                "Vin d'honneur",
                "Salle des Cailloux, Église Sainte-Mathilde",
                "33 Rue Lucien Voilin, 92800 Puteaux",
                14,
                0,
            ),
            "reception": (
                "Dîner",
                "Palais Groupe 91",
                "2 Rue Jules Guesde, 91130 Ris-Orangis",
                19,
                30,
            ),
        }
        for code, (name, venue, address, hour, minute) in expected.items():
            event = WeddingEvent.objects.get(code=code)
            local_start = timezone.localtime(
                event.starts_at,
                ZoneInfo("Europe/Paris"),
            )
            self.assertEqual(event.name, name)
            self.assertEqual(event.venue_name, venue)
            self.assertEqual(event.address, address)
            self.assertEqual((local_start.hour, local_start.minute), (hour, minute))
            self.assertTrue(event.map_url.startswith("https://www.google.com/maps/"))
