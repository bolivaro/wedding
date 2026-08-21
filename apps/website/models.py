from django.db import models


class StayArea(models.Model):
    name = models.CharField("nom", max_length=120)
    slug = models.SlugField(unique=True)
    summary = models.TextField("présentation")
    advantages = models.TextField("atouts", blank=True)
    considerations = models.TextField("points d'attention", blank=True)
    transport_notes = models.TextField("conseils de transport", blank=True)
    recommended_for = models.CharField("profil conseillé", max_length=240, blank=True)
    search_query = models.CharField("recherche Google Maps", max_length=240, blank=True)
    display_order = models.PositiveSmallIntegerField("ordre", default=0)
    checked_at = models.DateField("vérifié le", null=True, blank=True)
    is_published = models.BooleanField("publié", default=False)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "zone de séjour"
        verbose_name_plural = "zones de séjour"

    def __str__(self):
        return self.name


class Accommodation(models.Model):
    class Type(models.TextChoices):
        HOTEL = "hotel", "Hôtel"
        APARTHOTEL = "aparthotel", "Appart'hôtel"
        RENTAL = "rental", "Location saisonnière"

    area = models.ForeignKey(StayArea, on_delete=models.PROTECT, related_name="accommodations")
    name = models.CharField("nom", max_length=160)
    accommodation_type = models.CharField("type", max_length=20, choices=Type.choices)
    address = models.CharField("adresse", max_length=255, blank=True)
    booking_url = models.URLField("lien de réservation", max_length=1000)
    price_level = models.PositiveSmallIntegerField("niveau de prix", null=True, blank=True)
    capacity_note = models.CharField("capacité", max_length=120, blank=True)
    has_parking = models.BooleanField("stationnement", null=True)
    near_public_transport = models.BooleanField("proche des transports", null=True)
    is_accessible = models.BooleanField("accessible PMR", null=True)
    editorial_note = models.TextField("note", blank=True)
    checked_at = models.DateField("vérifié le", null=True, blank=True)
    display_order = models.PositiveSmallIntegerField("ordre", default=0)
    is_published = models.BooleanField("publié", default=False)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "logement"
        verbose_name_plural = "logements"

    def __str__(self):
        return self.name
