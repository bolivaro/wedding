from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse

from .forms import GuestImportUploadForm
from .models import (
    Guest,
    GuestEventInvitation,
    GuestImportBatch,
    GuestImportRow,
    WeddingEvent,
)
from .services.import_guests import analyze_batch, apply_batch, upload_checksum


class GuestEventInvitationInline(admin.TabularInline):
    model = GuestEventInvitation
    extra = 0


class CompanionInline(admin.TabularInline):
    model = Guest
    fk_name = "invitation_owner"
    extra = 0
    fields = ("first_name", "last_name", "gender", "is_active", "rsvp_status")
    show_change_link = True


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    change_list_template = "admin/guests/guest/change_list.html"
    list_display = (
        "full_name",
        "email",
        "guest_type",
        "guest_group",
        "invitation_kind",
        "party_size_limit",
        "rsvp_status",
        "is_active",
    )
    search_fields = ("first_name", "last_name", "email", "qr_token")
    list_filter = (
        "guest_type",
        "guest_group",
        "invitation_kind",
        "rsvp_status",
        "is_active",
        "is_invited",
        "is_vip",
    )
    readonly_fields = ("qr_token", "created_at", "updated_at")
    inlines = [GuestEventInvitationInline, CompanionInline]

    def get_urls(self):
        custom_urls = [
            path("import/", self.admin_site.admin_view(self.import_view), name="guests_guest_import"),
            path(
                "import/<int:batch_id>/preview/",
                self.admin_site.admin_view(self.import_preview_view),
                name="guests_guest_import_preview",
            ),
            path(
                "import/<int:batch_id>/confirm/",
                self.admin_site.admin_view(self.import_confirm_view),
                name="guests_guest_import_confirm",
            ),
        ]
        return custom_urls + super().get_urls()

    def _ensure_import_permission(self, request):
        if not self.has_change_permission(request):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied

    def import_view(self, request):
        self._ensure_import_permission(request)
        form = GuestImportUploadForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            uploaded_file = form.cleaned_data["file"]
            checksum = upload_checksum(uploaded_file)
            existing = GuestImportBatch.objects.filter(checksum=checksum).first()
            if existing:
                messages.info(request, "Ce fichier a déjà été analysé.")
                return redirect("admin:guests_guest_import_preview", batch_id=existing.pk)

            batch = GuestImportBatch.objects.create(
                file=uploaded_file,
                original_filename=uploaded_file.name,
                checksum=checksum,
                created_by=request.user,
            )
            analyze_batch(batch)
            return redirect("admin:guests_guest_import_preview", batch_id=batch.pk)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Importer des invités",
            "form": form,
        }
        return render(request, "admin/guests/guest/import_form.html", context)

    def import_preview_view(self, request, batch_id):
        self._ensure_import_permission(request)
        batch = get_object_or_404(GuestImportBatch, pk=batch_id)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Prévisualisation de l'import",
            "batch": batch,
            "rows": batch.rows.select_related("matched_guest"),
            "confirm_url": reverse(
                "admin:guests_guest_import_confirm",
                kwargs={"batch_id": batch.pk},
            ),
        }
        return render(request, "admin/guests/guest/import_preview.html", context)

    def import_confirm_view(self, request, batch_id):
        self._ensure_import_permission(request)
        if request.method != "POST":
            return HttpResponseRedirect(
                reverse("admin:guests_guest_import_preview", kwargs={"batch_id": batch_id})
            )
        batch = get_object_or_404(GuestImportBatch, pk=batch_id)
        try:
            apply_batch(batch)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "L'import a été appliqué avec succès.")
        return redirect("admin:guests_guest_import_preview", batch_id=batch.pk)


@admin.register(WeddingEvent)
class WeddingEventAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "starts_at", "capacity", "is_active")
    list_editable = ("capacity", "is_active")
    ordering = ("display_order",)


class GuestImportRowInline(admin.TabularInline):
    model = GuestImportRow
    extra = 0
    can_delete = False
    fields = ("sheet_name", "row_number", "outcome", "matched_guest", "messages")
    readonly_fields = fields


@admin.register(GuestImportBatch)
class GuestImportBatchAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "status", "created_by", "created_at", "applied_at")
    search_fields = ("original_filename", "checksum")
    list_filter = ("status",)
    readonly_fields = (
        "file",
        "original_filename",
        "checksum",
        "status",
        "summary",
        "error_message",
        "created_by",
        "created_at",
        "applied_at",
    )
    inlines = [GuestImportRowInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
