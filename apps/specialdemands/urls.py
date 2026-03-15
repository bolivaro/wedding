from django.urls import path
from . import views

app_name = "specialdemands"

urlpatterns = [
    path("", views.home, name="specialdemands_home"),
    path("special-demand/<uuid:token>/", views.special_demand_detail, name="detail"),
    path("special-demand/<uuid:token>/respond/", views.special_demand_respond, name="respond"),
]