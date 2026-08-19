from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .forms import GuestImportUploadForm
from .models import (
    Guest,
    GuestEventInvitation,
    GuestImportBatch,
    GuestImportRow,
    Ticket,
    WeddingEvent,
)
from .services.import_guests import analyze_batch, apply_batch, upload_checksum
from .services.access import issue_guest_access, start_guest_session
from .services.ticket import TicketGenerationError, generate_ticket


class GuestEventInvitationInline(admin.TabularInline):
    model = GuestEventInvitation
    extra = 0


class CompanionInline(admin.TabularInline):
    model = Guest
    fk_name = "invitation_owner"
    extra = 0
    fields = ("first_name", "last_name", "gender", "is_active", "rsvp_status")
    show_change_link = True


class TicketInline(admin.StackedInline):
    model = Ticket
    extra = 0
    can_delete = False
    fields = (
        "status",
        "jpg_file",
        "pdf_file",
        "template_version",
        "generated_at",
        "last_error",
    )
    readonly_fields = fields

    def get_queryset(self, request):
        return super().get_queryset(request).filter(guest__invitation_owner__isnull=True)


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
        "access_status",
        "qr_public_link",
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
    readonly_fields = (
        "qr_token",
        "rsvp_quick_access",
        "qr_quick_access",
        "created_at",
        "updated_at",
    )
    inlines = [GuestEventInvitationInline, CompanionInline, TicketInline]
    actions = ["regenerate_rsvp_access", "generate_selected_tickets"]
    list_select_related = ("invitation_owner",)

    @admin.display(description="Accès RSVP")
    def access_status(self, obj):
        if obj.invitation_owner_id:
            owner = obj.invitation_owner
            credential = self._usable_access(owner)
            if credential:
                return format_html(
                    "Via {} · <a href=\"{}\" target=\"_blank\" rel=\"noopener\">Ouvrir RSVP ↗</a>",
                    owner.full_name,
                    reverse("admin:guests_guest_open_rsvp", kwargs={"guest_id": owner.pk}),
                )
            return f"Via {owner.full_name} — accès indisponible"
        credential = obj.access_credentials.order_by("-created_at").first()
        if not credential:
            return "Non généré"
        if not credential.is_usable(timezone.now()):
            return "Expiré, révoqué ou verrouillé"
        return format_html(
            "Valide jusqu'au {} · <a href=\"{}\" target=\"_blank\" rel=\"noopener\">Ouvrir RSVP ↗</a>",
            credential.expires_at.strftime("%d/%m/%Y"),
            reverse("admin:guests_guest_open_rsvp", kwargs={"guest_id": obj.pk}),
        )

    @admin.display(description="Accès rapide au RSVP")
    def rsvp_quick_access(self, obj):
        if not obj or not obj.pk:
            return "Enregistrez d'abord l'invité."
        owner = obj.invitation_owner or obj
        if not self._usable_access(owner):
            return "Aucun accès RSVP actif. Générez-en un depuis la liste des invités."
        return format_html(
            "<a class=\"button\" href=\"{}\" target=\"_blank\" rel=\"noopener\">Ouvrir le RSVP sans régénérer</a>",
            reverse("admin:guests_guest_open_rsvp", kwargs={"guest_id": owner.pk}),
        )

    @admin.display(description="QR public")
    def qr_public_link(self, obj):
        owner = obj.invitation_owner or obj
        if not obj.is_active or not owner.is_active:
            return "Invité inactif"
        return format_html(
            "{}<a href=\"{}\" target=\"_blank\" rel=\"noopener\">Tester le QR du groupe ↗</a>",
            "Via l'invité principal · " if obj.invitation_owner_id else "",
            reverse("guests:public_qr_landing", kwargs={"token": owner.qr_token}),
        )

    @admin.display(description="Test du QR permanent")
    def qr_quick_access(self, obj):
        if not obj or not obj.pk:
            return "Enregistrez d'abord l'invité."
        owner = obj.invitation_owner or obj
        if not obj.is_active or not owner.is_active:
            return "Le QR d'un invité inactif n'est pas reconnu publiquement."
        return format_html(
            "<a class=\"button\" href=\"{}\" target=\"_blank\" rel=\"noopener\">Ouvrir la page du QR du groupe</a>",
            reverse("guests:public_qr_landing", kwargs={"token": owner.qr_token}),
        )

    @staticmethod
    def _usable_access(guest):
        now = timezone.now()
        for credential in guest.access_credentials.order_by("-created_at"):
            if credential.is_usable(now):
                return credential
        return None

    @admin.action(description="Régénérer l'accès des invités principaux sélectionnés")
    def regenerate_rsvp_access(self, request, queryset):
        links = []
        selected = queryset.select_related("invitation_owner")
        companions = list(selected.filter(invitation_owner__isnull=False))
        inactive_guests = list(
            selected.filter(invitation_owner__isnull=True, is_active=False)
        )

        for guest in selected.filter(invitation_owner__isnull=True, is_active=True):
            issued = issue_guest_access(guest=guest, created_by=request.user)
            path = reverse(
                "guests:access_entry",
                kwargs={
                    "selector": issued.credential.selector,
                    "secret": issued.secret,
                },
            )
            links.append((guest.full_name, request.build_absolute_uri(path)))
        if links:
            self.message_user(
                request,
                format_html_join(
                    "<br>",
                    "{} : <a href=\"{}\">{}</a>",
                    ((name, url, url) for name, url in links),
                ),
                level=messages.WARNING,
            )
        if companions:
            self.message_user(
                request,
                format_html_join(
                    "<br>",
                    "{} — accès géré par l'invité principal {}",
                    (
                        (companion.full_name, companion.invitation_owner.full_name)
                        for companion in companions
                    ),
                ),
                level=messages.INFO,
            )
        if inactive_guests:
            self.message_user(
                request,
                "Les invités principaux inactifs ont été ignorés.",
                level=messages.INFO,
            )

    @admin.action(description="Générer les billets sélectionnés")
    def generate_selected_tickets(self, request, queryset):
        generated = 0
        failed = []
        owners = {}
        for guest in queryset.filter(is_active=True).select_related("invitation_owner"):
            owner = guest.invitation_owner or guest
            if owner.is_active:
                owners[owner.pk] = owner
        for guest in owners.values():
            try:
                generate_ticket(guest)
            except TicketGenerationError:
                failed.append(guest.full_name)
            else:
                generated += 1
        if generated:
            self.message_user(
                request,
                f"{generated} billet(s) de groupe prêt(s).",
                messages.SUCCESS,
            )
        if failed:
            self.message_user(
                request,
                f"Échec pour : {', '.join(failed)}.",
                messages.ERROR,
            )

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
            path(
                "<int:guest_id>/open-rsvp/",
                self.admin_site.admin_view(self.open_rsvp_view),
                name="guests_guest_open_rsvp",
            ),
        ]
        return custom_urls + super().get_urls()

    def open_rsvp_view(self, request, guest_id):
        guest = get_object_or_404(
            Guest.objects.select_related("invitation_owner"),
            pk=guest_id,
        )
        owner = guest.invitation_owner or guest
        if not self.has_view_permission(request, owner):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        credential = self._usable_access(owner)
        if not credential:
            messages.error(
                request,
                "Cet invité ne possède aucun accès RSVP actif.",
            )
            return redirect("admin:guests_guest_change", object_id=owner.pk)
        start_guest_session(request, credential)
        return redirect("guests:rsvp_dashboard")

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


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("guest", "status", "template_version", "generated_at", "updated_at")
    list_filter = ("status", "template_version")
    search_fields = ("guest__first_name", "guest__last_name", "guest__email")
    readonly_fields = (
        "guest",
        "status",
        "jpg_file",
        "pdf_file",
        "template_version",
        "template_checksum",
        "render_signature",
        "generated_at",
        "last_error",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
