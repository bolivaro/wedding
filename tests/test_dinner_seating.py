from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from guests.models import DinnerTable, DinnerSeatingAssignment, Guest, GuestEventInvitation, WeddingEvent
from guests.services.seating import assign_guests, create_table, dinner_guests, exchange_guests


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class DinnerSeatingTests(TestCase):
    def setUp(self):
        self.event = WeddingEvent.objects.get(code=WeddingEvent.Code.RECEPTION)
        self.table = create_table(number=1, name="Olivier")
        self.other = create_table(number=2)

    def guest(self, name, status=Guest.RSVPStatus.ATTENDING, **kwargs):
        guest = Guest.objects.create(first_name=name, rsvp_status=status, **kwargs)
        GuestEventInvitation.objects.create(guest=guest, event=self.event, attendance_status=status)
        return guest

    def test_only_confirmed_effective_dinner_attendance_is_selectable(self):
        present = self.guest("Présent")
        self.guest("En attente", Guest.RSVPStatus.PENDING)
        absent = self.guest("Absent", Guest.RSVPStatus.NOT_ATTENDING)
        absent.event_invitations.update(attendance_status=Guest.RSVPStatus.ATTENDING)
        self.guest("Inactif", is_active=False)
        ineligible = self.guest("Non éligible")
        ineligible.event_invitations.update(is_eligible=False, attendance_status=Guest.RSVPStatus.PENDING)
        self.assertEqual(list(dinner_guests()), [present])
        with self.assertRaises(ValidationError):
            assign_guests(guest_ids=[present.pk, absent.pk], table_id=self.table.pk)
        self.assertFalse(DinnerSeatingAssignment.objects.exists())

    def test_inherited_absence_excludes_companion_but_custom_presence_is_kept(self):
        owner = self.guest("Principal", Guest.RSVPStatus.NOT_ATTENDING)
        inherited = self.guest("Hérité", invitation_owner=owner)
        custom = self.guest("Personnalisé", invitation_owner=owner, attendance_mode=Guest.AttendanceMode.CUSTOM)
        self.assertNotIn(inherited, dinner_guests())
        self.assertIn(custom, dinner_guests())

    def test_capacity_and_group_assignment_are_atomic(self):
        guests = [self.guest(str(i)) for i in range(12)]
        assign_guests(guest_ids=[g.pk for g in guests[:9]], table_id=self.table.pk)
        with self.assertRaises(ValidationError):
            assign_guests(guest_ids=[g.pk for g in guests[9:]], table_id=self.table.pk)
        self.assertEqual(self.table.assignments.count(), 9)
        self.assertFalse(DinnerSeatingAssignment.objects.filter(guest__in=guests[9:]).exists())
        assign_guests(guest_ids=[guests[0].pk], table_id=self.table.pk)
        self.assertEqual(self.table.assignments.count(), 9)

    def test_move_and_exchange_full_tables(self):
        guests = [self.guest(str(i)) for i in range(20)]
        assign_guests(guest_ids=[g.pk for g in guests[:10]], table_id=self.table.pk)
        assign_guests(guest_ids=[g.pk for g in guests[10:]], table_id=self.other.pk)
        exchange_guests(first_id=guests[0].pk, second_id=guests[10].pk)
        self.assertEqual(DinnerSeatingAssignment.objects.get(guest=guests[0]).table, self.other)
        self.assertEqual(self.table.assignments.count(), 10)
        with self.assertRaises(ValidationError):
            assign_guests(guest_ids=[guests[1].pk], table_id=self.other.pk)

    def test_admin_page_actions_anomalies_and_validation(self):
        self.client.force_login(get_user_model().objects.create_superuser(username="planner", password="test"))
        url = reverse("admin:guests_guest_seating")
        guest = self.guest("Camille")
        response = self.client.get(url)
        self.assertContains(response, "Camille")
        self.assertEqual(self.client.post(url, {"action": "assign", "table_id": self.table.pk, "guest_ids": [guest.pk]}).status_code, 302)
        guest.is_active = False
        guest.save()
        self.assertContains(self.client.get(url), "À vérifier")
        self.assertEqual(self.client.post(url, {"action": "assign", "table_id": "invalid"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code, 400)
        self.client.post(url, {"action": "remove", "guest_id": guest.pk})
        self.assertFalse(DinnerSeatingAssignment.objects.exists())

    def test_view_only_admin_cannot_mutate(self):
        from django.contrib.auth.models import Permission
        user = get_user_model().objects.create_user(username="viewer", is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename="view_guest"))
        self.client.force_login(user)
        url = reverse("admin:guests_guest_seating")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"action": "create", "number": 3}).status_code, 403)

    def test_duplicate_table_number_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_table(number=1)
