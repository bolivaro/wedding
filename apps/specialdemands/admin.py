from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.conf import settings
from .models import SpecialDemand, SpecialDemandSlide

class SpecialDemandSlideInline(admin.TabularInline):
    model = SpecialDemandSlide
    extra = 1


@admin.register(SpecialDemand)
class SpecialDemandAdmin(admin.ModelAdmin):
    list_display = (
        "guest",
        "demand_type",
        "request_owner",
        "status",
        "public_link",
        "created_at",
        "responded_at",
    )
    list_filter = ("demand_type", "request_owner", "status", "created_by")
    search_fields = (
        "guest__first_name",
        "guest__last_name",
        "guest__email",
        "token",
        "created_by__username",
    )
    readonly_fields = (
        "token",
        "created_at",
        "responded_at",
        "created_by",
        "public_link",
        "public_url",
    )
    inlines = [SpecialDemandSlideInline]

    fieldsets = (
        ("Informations générales", {
            "fields": (
                "guest",
                "demand_type",
                "request_owner",
                "status",
                "final_question",
                "notify_emails",
            )
        }),
        ("Accès public", {
            "fields": (
                "token",
                "public_link",
                "public_url",
            )
        }),
        ("Traçabilité", {
            "fields": (
                "created_by",
                "created_at",
                "responded_at",
            )
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Lien public")
    def public_link(self, obj):
        return format_html('<a href="{}" target="_blank">Ouvrir la demande</a>', obj.get_absolute_url())

    @admin.display(description="URL")
    def public_url(self, obj):
        return obj.get_absolute_url()