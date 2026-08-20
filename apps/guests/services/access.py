import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from guests.models import GuestAccessCredential


GUEST_SESSION_KEY = "guest_access_guest_id"
CREDENTIAL_SESSION_KEY = "guest_access_credential_id"


@dataclass(frozen=True)
class IssuedGuestAccess:
    credential: GuestAccessCredential
    secret: str


@transaction.atomic
def issue_guest_access(*, guest, created_by=None, expires_at=None):
    if guest.invitation_owner_id:
        raise ValidationError("Les accompagnants n'ont pas d'accès RSVP autonome.")
    now = timezone.now()
    GuestAccessCredential.objects.select_for_update().filter(
        guest=guest,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    secret = secrets.token_urlsafe(32)
    credential = GuestAccessCredential.objects.create(
        guest=guest,
        secret_hash=make_password(secret),
        expires_at=expires_at or now + timedelta(days=settings.GUEST_ACCESS_LIFETIME_DAYS),
        created_by=created_by,
    )
    return IssuedGuestAccess(credential=credential, secret=secret)


@transaction.atomic
def authenticate_guest_access(*, selector, secret, at=None):
    now = at or timezone.now()
    try:
        credential = GuestAccessCredential.objects.select_for_update().select_related("guest").get(
            selector=selector
        )
    except (GuestAccessCredential.DoesNotExist, ValueError, ValidationError):
        return None

    if not credential.is_usable(now):
        return None
    if not check_password(secret, credential.secret_hash):
        credential.failed_attempts += 1
        update_fields = ["failed_attempts"]
        if credential.failed_attempts >= settings.GUEST_ACCESS_MAX_FAILURES:
            credential.locked_until = now + timedelta(minutes=settings.GUEST_ACCESS_LOCK_MINUTES)
            credential.failed_attempts = 0
            update_fields.extend(["locked_until"])
        credential.save(update_fields=update_fields)
        return None

    credential.failed_attempts = 0
    credential.locked_until = None
    credential.last_used_at = now
    credential.save(update_fields=["failed_attempts", "locked_until", "last_used_at"])
    return credential


def start_guest_session(request, credential):
    request.session.cycle_key()
    request.session[GUEST_SESSION_KEY] = credential.guest_id
    request.session[CREDENTIAL_SESSION_KEY] = credential.pk


def clear_guest_session(request):
    request.session.pop(GUEST_SESSION_KEY, None)
    request.session.pop(CREDENTIAL_SESSION_KEY, None)


def get_session_guest(request, *, at=None):
    guest_id = request.session.get(GUEST_SESSION_KEY)
    credential_id = request.session.get(CREDENTIAL_SESSION_KEY)
    if not guest_id or not credential_id:
        return None
    now = at or timezone.now()
    credential = GuestAccessCredential.objects.select_related("guest").filter(
        pk=credential_id,
        guest_id=guest_id,
    ).first()
    if not credential or not credential.is_usable(now):
        clear_guest_session(request)
        return None
    return credential.guest


@transaction.atomic
def revoke_guest_access(*, credential):
    credential = GuestAccessCredential.objects.select_for_update().get(pk=credential.pk)
    if credential.revoked_at is None:
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["revoked_at"])
    return credential
