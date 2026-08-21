from django.contrib import admin

from .models import Accommodation, StayArea


class AccommodationInline(admin.TabularInline):
    model = Accommodation
    extra = 0


@admin.register(StayArea)
class StayAreaAdmin(admin.ModelAdmin):
    list_display = ("name", "recommended_for", "display_order", "checked_at", "is_published")
    list_editable = ("display_order", "is_published")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (AccommodationInline,)


@admin.register(Accommodation)
class AccommodationAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "accommodation_type", "checked_at", "is_published")
    list_filter = ("area", "accommodation_type", "is_published")
    search_fields = ("name", "address")
