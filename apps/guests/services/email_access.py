import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from guests.models import Guest, GuestEmailToken


@dataclass(frozen=True)
class IssuedEmailToken:
    token: GuestEmailToken
    secret: str


def normalize_email(email):
    return str(email or "").strip().casefold()


@transaction.atomic
def request_email_verification(*, guest, email):
    email = normalize_email(email)
    if not email:
        raise ValidationError("Une adresse email est requise.")
    if Guest.objects.exclude(pk=guest.pk).filter(email__iexact=email).exists():
        raise ValidationError("Cette adresse email est déjà utilisée.")

    guest.pending_email = email
    guest.save(update_fields=["pending_email", "updated_at"])
    GuestEmailToken.objects.filter(
        guest=guest,
        purpose=GuestEmailToken.Purpose.VERIFY,
        used_at__isnull=True,
    ).update(used_at=timezone.now())
    return _issue_email_token(
        guest=guest,
        purpose=GuestEmailToken.Purpose.VERIFY,
        target_email=email,
    )


def issue_recovery_token(*, guest):
    if not guest.email or not guest.email_verified_at:
        raise ValidationError("La récupération nécessite un email vérifié.")
    return _issue_email_token(
        guest=guest,
        purpose=GuestEmailToken.Purpose.RECOVER,
        target_email=guest.email,
    )


def _issue_email_token(*, guest, purpose, target_email):
    secret = secrets.token_urlsafe(32)
    token = GuestEmailToken.objects.create(
        guest=guest,
        purpose=purpose,
        target_email=target_email,
        secret_hash=make_password(secret),
        expires_at=timezone.now() + timedelta(minutes=settings.GUEST_EMAIL_TOKEN_MINUTES),
    )
    return IssuedEmailToken(token=token, secret=secret)


@transaction.atomic
def consume_email_token(*, selector, secret, purpose):
    now = timezone.now()
    token = GuestEmailToken.objects.select_for_update().select_related("guest").filter(
        selector=selector,
        purpose=purpose,
        used_at__isnull=True,
        expires_at__gt=now,
    ).first()
    if not token or not check_password(secret, token.secret_hash):
        return None
    token.used_at = now
    token.save(update_fields=["used_at"])

    if purpose == GuestEmailToken.Purpose.VERIFY:
        guest = token.guest
        if guest.pending_email != token.target_email:
            return None
        if Guest.objects.exclude(pk=guest.pk).filter(email__iexact=token.target_email).exists():
            raise ValidationError("Cette adresse email est déjà utilisée.")
        guest.email = token.target_email
        guest.pending_email = ""
        guest.email_verified_at = now
        guest.save(update_fields=["email", "pending_email", "email_verified_at", "updated_at"])
    return token
