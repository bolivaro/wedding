import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Guest(models.Model):
    class GuestType(models.TextChoices):
        REGULAR = "regular", "Invité classique"
        HONOR = "honor", "Personne d'honneur"
        WITNESS = "witness", "Témoin"
        PARENT = "parent", "Parent"

    class Gender(models.TextChoices):
        MALE = "male", "Homme"
        FEMALE = "female", "Femme"
        OTHER = "other", "Autre"
        UNSPECIFIED = "unspecified", "Non renseigné"

    class GuestGroup(models.TextChoices):
        BRIDE_FAMILY = "bride_family", "Famille femme"
        GROOM_FAMILY = "groom_family", "Famille mari"
        BRIDE_FRIENDS = "bride_friends", "Amis femme"
        GROOM_FRIENDS = "groom_friends", "Amis mari"

    class InvitationKind(models.TextChoices):
        SINGLE = "single", "Individuelle"
        COUPLE = "couple", "Couple"
        FAMILY = "family", "Famille"

    class RSVPStatus(models.TextChoices):
        PENDING = "pending", "En attente"
        ATTENDING = "attending", "Présent"
        NOT_ATTENDING = "not_attending", "Absent"

    class RSVPSource(models.TextChoices):
        EXCEL = "excel", "Import Excel"
        GUEST = "guest", "Invité"
        ADMIN = "admin", "Administration"

    first_name = models.CharField("prénom", max_length=100)
    last_name = models.CharField("nom", max_length=100, blank=True)
    email = models.EmailField("email", unique=True, null=True, blank=True)
    pending_email = models.EmailField("nouvel email à vérifier", blank=True)
    email_verified_at = models.DateTimeField(
        "email vérifié le",
        null=True,
        blank=True,
    )

    is_invited = models.BooleanField("invité classique", default=True)
    is_vip = models.BooleanField("invité VIP", default=False)

    guest_type = models.CharField(
        "type d'invité",
        max_length=20,
        choices=GuestType.choices,
        null=True,
        blank=True,
    )
    gender = models.CharField(
        "genre",
        max_length=20,
        choices=Gender.choices,
        default=Gender.UNSPECIFIED,
    )
    guest_group = models.CharField(
        "groupe d'invités",
        max_length=30,
        choices=GuestGroup.choices,
        blank=True,
    )
    invitation_kind = models.CharField(
        "nature de l'invitation",
        max_length=20,
        choices=InvitationKind.choices,
        default=InvitationKind.SINGLE,
    )
    party_size_limit = models.PositiveSmallIntegerField(
        "nombre total de places autorisées",
        default=1,
        help_text="Inclut l'invité principal.",
    )
    invitation_owner = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="companions",
        null=True,
        blank=True,
        verbose_name="invité principal",
    )

    has_been_contacted = models.BooleanField("contacté", null=True, blank=True)
    requires_visa = models.BooleanField("soumis au visa", null=True, blank=True)
    age_category = models.CharField("catégorie d'âge", max_length=50, blank=True)
    origin_country = models.CharField("origine", max_length=100, blank=True)
    travel_origin_country = models.CharField(
        "provenance",
        max_length=100,
        blank=True,
    )

    rsvp_status = models.CharField(
        "statut RSVP",
        max_length=20,
        choices=RSVPStatus.choices,
        default=RSVPStatus.PENDING,
    )
    rsvp_source = models.CharField(
        "source du RSVP",
        max_length=20,
        choices=RSVPSource.choices,
        blank=True,
    )
    rsvp_responded_at = models.DateTimeField(
        "RSVP répondu le",
        null=True,
        blank=True,
    )

    qr_token = models.UUIDField(
        "identifiant QR permanent",
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    is_active = models.BooleanField("actif", default=True)

    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("mis à jour le", auto_now=True)

    class Meta:
        ordering = ["first_name", "last_name"]
        verbose_name = "invité"
        verbose_name_plural = "invités"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(invitation_kind="single", party_size_limit=1)
                    | models.Q(invitation_kind="couple", party_size_limit=2)
                    | models.Q(invitation_kind="family", party_size_limit__gte=2)
                ),
                name="guest_valid_party_size_for_kind",
            ),
        ]

    def __str__(self):
        return self.full_name or self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def salutation(self):
        if self.gender == self.Gender.MALE:
            return "M."
        if self.gender == self.Gender.FEMALE:
            return "Mme"
        return ""

    @property
    def companion_limit(self):
        if self.invitation_owner_id:
            return 0
        return max(0, self.party_size_limit - 1)

    def clean(self):
        super().clean()
        errors = {}

        if self.invitation_owner_id and self.invitation_owner_id == self.pk:
            errors["invitation_owner"] = "Un invité ne peut pas être son propre accompagnant."

        if self.invitation_kind == self.InvitationKind.SINGLE and self.party_size_limit != 1:
            errors["party_size_limit"] = "Une invitation individuelle autorise exactement une place."
        elif self.invitation_kind == self.InvitationKind.COUPLE and self.party_size_limit != 2:
            errors["party_size_limit"] = "Une invitation couple autorise exactement deux places."
        elif self.invitation_kind == self.InvitationKind.FAMILY and self.party_size_limit < 2:
            errors["party_size_limit"] = "Une invitation famille doit autoriser au moins deux places."

        if errors:
            raise ValidationError(errors)


class WeddingEvent(models.Model):
    class Code(models.TextChoices):
        CITY_HALL = "city_hall", "Mairie"
        CHURCH = "church", "Église"
        RECEPTION = "reception", "Soirée"

    code = models.CharField("code", max_length=30, choices=Code.choices, unique=True)
    name = models.CharField("nom", max_length=100)
    starts_at = models.DateTimeField("début", null=True, blank=True)
    capacity = models.PositiveIntegerField("capacité", null=True, blank=True)
    display_order = models.PositiveSmallIntegerField("ordre", default=0)
    is_active = models.BooleanField("actif", default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "événement du mariage"
        verbose_name_plural = "événements du mariage"

    def __str__(self):
        return self.name


class GuestEventInvitation(models.Model):
    guest = models.ForeignKey(
        Guest,
        on_delete=models.CASCADE,
        related_name="event_invitations",
        verbose_name="invité",
    )
    event = models.ForeignKey(
        WeddingEvent,
        on_delete=models.PROTECT,
        related_name="guest_invitations",
        verbose_name="événement",
    )
    is_eligible = models.BooleanField("éligible", default=True)
    attendance_status = models.CharField(
        "présence",
        max_length=20,
        choices=Guest.RSVPStatus.choices,
        default=Guest.RSVPStatus.PENDING,
    )
    response_source = models.CharField(
        "source de la réponse",
        max_length=20,
        choices=Guest.RSVPSource.choices,
        blank=True,
    )
    responded_at = models.DateTimeField("répondu le", null=True, blank=True)

    class Meta:
        ordering = ["event__display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["guest", "event"],
                name="unique_guest_event_invitation",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_eligible=True)
                    | ~models.Q(attendance_status=Guest.RSVPStatus.ATTENDING)
                ),
                name="ineligible_guest_cannot_attend_event",
            ),
        ]
        verbose_name = "invitation à un événement"
        verbose_name_plural = "invitations aux événements"

    def clean(self):
        super().clean()
        if not self.is_eligible and self.attendance_status == Guest.RSVPStatus.ATTENDING:
            raise ValidationError(
                {"attendance_status": "Un invité non éligible ne peut pas confirmer sa présence."}
            )

    def __str__(self):
        return f"{self.guest} — {self.event}"
