from django.urls import path

from . import views


app_name = "guests"

urlpatterns = [
    path("access/invalid/", views.access_invalid, name="access_invalid"),
    path("access/<uuid:selector>/<str:secret>/", views.access_entry, name="access_entry"),
    path("access/recover/", views.recovery_request, name="recovery_request"),
    path(
        "access/recover/<uuid:selector>/<str:secret>/",
        views.recovery_consume,
        name="recovery_consume",
    ),
    path("rsvp/", views.rsvp_dashboard, name="rsvp_dashboard"),
    path("rsvp/respond/", views.rsvp_respond, name="rsvp_respond"),
    path("rsvp/companions/add/", views.companion_add, name="companion_add"),
    path(
        "rsvp/companions/<int:companion_id>/remove/",
        views.companion_remove,
        name="companion_remove",
    ),
    path("rsvp/email/", views.email_update, name="email_update"),
    path("email/verify/<uuid:selector>/<str:secret>/", views.verify_email, name="verify_email"),
    path("ticket/preview/", views.ticket_preview, name="ticket_preview"),
    path("ticket/generate/", views.ticket_generate_all, name="ticket_generate_all"),
    path(
        "ticket/<int:guest_id>/generate/",
        views.ticket_generate,
        name="ticket_generate",
    ),
    path(
        "ticket/<int:guest_id>/image/",
        views.ticket_image,
        name="ticket_image",
    ),
    path(
        "ticket/<int:guest_id>/<str:file_format>/",
        views.ticket_download,
        name="ticket_download",
    ),
    path("ticket/party/pdf/", views.party_ticket_download, name="party_ticket_download"),
    path(
        "ticket/informations/jpg/",
        views.ticket_information_download,
        name="ticket_information_download",
    ),
    path("ticket/email/", views.ticket_email, name="ticket_email"),
    path("q/<uuid:token>/", views.public_qr_landing, name="public_qr_landing"),
]
