from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from locations.models import City
from rates.models import CargoType

from .decorators import forwarder_required, staff_permission_required


@login_required
@forwarder_required
@staff_permission_required('can_view_rates')
def load_cargo_types(request):
    transport_mode = request.GET.get('transport_mode')
    cargo_types_list = list(CargoType.objects.filter(transport_mode=transport_mode).values('id', 'name'))
    return JsonResponse(cargo_types_list, safe=False)


@login_required
@forwarder_required
def load_cities(request):
    province_id = request.GET.get('province_id')
    if province_id:
        cities = City.objects.filter(province_id=province_id).order_by('name')
        city_list = list(cities.values('id', 'name'))
        return JsonResponse(city_list, safe=False)
    return JsonResponse([], safe=False)
