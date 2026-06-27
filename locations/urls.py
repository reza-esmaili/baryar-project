from django.urls import path
from . import views

app_name = 'locations'

urlpatterns = [
    # مسیرهای AJAX
    path('ajax/provinces/', views.load_provinces, name='ajax_load_provinces'),
    path('ajax/cities/', views.load_cities, name='ajax_load_cities'),
    path('ajax/countries/', views.load_countries_with_rates, name='ajax_load_countries'),
    path('ajax/destination-cities/', views.load_destination_cities, name='ajax_load_destination_cities'),
    path('ajax/ports/', views.load_ports, name='ajax_load_ports'),
]
