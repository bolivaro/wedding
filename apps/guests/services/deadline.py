from django.conf import settings
from django.utils import timezone


def is_rsvp_open(*, at=None):
    current_time = at or timezone.now()
    return current_time <= settings.RSVP_DEADLINE
