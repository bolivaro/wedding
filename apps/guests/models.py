from django.db import models


class Guest(models.Model):
    first_name = models.CharField("prénom", max_length=100)
    last_name = models.CharField("nom", max_length=100, blank=True)
    email = models.EmailField("email", unique=True)

    is_invited = models.BooleanField("invité classique", default=True)
    is_vip = models.BooleanField("invité VIP", default=False)

    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("mis à jour le", auto_now=True)

    class Meta:
        ordering = ["first_name", "last_name"]
        verbose_name = "invité"
        verbose_name_plural = "invités"

    def __str__(self):
        return self.full_name or self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

