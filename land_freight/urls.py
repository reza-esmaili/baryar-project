from django.urls import path

from . import views

app_name = "land_freight"

urlpatterns = [
    path("", views.request_list, name="request_list"),
    path("new/", views.request_create, name="request_create"),
    path("<int:pk>/", views.request_detail, name="request_detail"),
    path("<int:pk>/status/", views.request_status, name="request_status"),
    path("<int:pk>/cancel/", views.request_cancel, name="request_cancel"),
    path("<int:pk>/republish/", views.request_republish, name="request_republish"),

    path("ajax/cities/", views.ajax_cities, name="ajax_cities"),
    path("ajax/foreign-cities/", views.ajax_foreign_cities, name="ajax_foreign_cities"),
    path("ajax/border-crossings/", views.ajax_border_crossings, name="ajax_border_crossings"),
]
