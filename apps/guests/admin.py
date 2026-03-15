from django.contrib import admin
from .models import Guest

@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "is_invited", "is_vip", "created_at")
    search_fields = ("first_name", "last_name", "email")
    list_filter = ("is_invited", "is_vip")
