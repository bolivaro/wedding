import uuid
from django.db import models
from django.conf import settings
from django.urls import reverse


class SpecialDemand(models.Model):
    DEMAND_TYPE_CHOICES = [
        ("witness", "Témoin"),
        ("maid_of_honor", "Femme d'honneur"),
        ("best_man", "Homme d'honneur"),
    ]

    STATUS_CHOICES = [
        ("pending", "En attente"),
        ("accepted", "Acceptée"),
        ("declined", "Refusée"),
    ]

    REQUEST_OWNER_CHOICES = [
        ("groom", "Marié"),
        ("bride", "Mariée"),
        ("couple", "Les deux"),
    ]

    guest = models.ForeignKey(
        "guests.Guest",
        on_delete=models.CASCADE,
        related_name="special_demands",
        verbose_name="invité"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_special_demands",
        verbose_name="créée par"
    )

    demand_type = models.CharField(
        "type de demande",
        max_length=30,
        choices=DEMAND_TYPE_CHOICES
    )

    request_owner = models.CharField(
        "demande portée par",
        max_length=20,
        choices=REQUEST_OWNER_CHOICES,
        default="couple"
    )

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    final_question = models.CharField(
        "question finale",
        max_length=255,
        default="Alors… accepterais-tu ? 💍"
    )

    status = models.CharField(
        "statut",
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    destination_emails = []
    if getattr(settings, "SPECIAL_DEMAND_DEFAULT_NOTIFY_EMAILS", None):
        destination_emails.extend(settings.SPECIAL_DEMAND_DEFAULT_NOTIFY_EMAILS)

    notify_emails = models.TextField(
        "emails à notifier",
        blank=True,
        help_text="Adresses email séparées par des virgules",
        default= ", ".join(destination_emails) if destination_emails else ""
    )

    responded_at = models.DateTimeField("répondu le", null=True, blank=True)
    created_at = models.DateTimeField("créé le", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "demande spéciale"
        verbose_name_plural = "demandes spéciales"

    def get_absolute_url(self):
        return reverse("specialdemands:detail", kwargs={"token": self.token})
    
    def __str__(self):
        return f"{self.guest.full_name} - {self.get_demand_type_display()}"

class SpecialDemandSlide(models.Model):
    special_demand = models.ForeignKey(
        SpecialDemand,
        on_delete=models.CASCADE,
        related_name="slides",
        verbose_name="demande spéciale"
    )
    position = models.PositiveIntegerField("position")
    title = models.CharField("titre", max_length=255, blank=True)
    text = models.TextField("texte")
    image = models.ImageField("image", upload_to="specialdemands/slides/")

    class Meta:
        ordering = ["position"]
        unique_together = ("special_demand", "position")
        verbose_name = "slide de demande spéciale"
        verbose_name_plural = "slides de demandes spéciales"

    def __str__(self):
        return f"{self.special_demand} - slide {self.position}"
