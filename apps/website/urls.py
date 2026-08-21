from django.urls import path

from . import views


app_name = "website"

urlpatterns = [
    path("", views.home, name="home"),
    path("programme/", views.program, name="program"),
    path("dress-code/", views.dress_code, name="dress_code"),
    path("sejour/", views.stay, name="stay"),
    path("mon-invitation/", views.my_invitation, name="my_invitation"),
]
