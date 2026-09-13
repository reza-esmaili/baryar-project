# admin_dashboard/views_ajax.py
#
# اندپوینت‌های JSON برای dropdown های وابسته (استان→شهر، کشور→شهر مقصد،
# شهر مقصد→پورت). این‌ها معادل نسخه‌ی documents/views.py هستند (بهترین نسخه‌ی
# موجود در پروژه: هم is_active را فیلتر می‌کند، هم برچسب پورت را با کد آن
# غنی می‌کند) به‌علاوه‌ی فیلتر بر اساس روش حمل مثل rates/views.py.

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from locations.models import City, DestinationCity, Port
from rates.models import CargoType

from .decorators import platform_staff_required


@login_required
@platform_staff_required
def ajax_cities(request):
    province_id = request.GET.get("province_id")
    if not province_id:
        return JsonResponse([], safe=False)
    cities = City.objects.filter(province_id=province_id, is_active=True).order_by("name").values("id", "name")
    return JsonResponse(list(cities), safe=False)


@login_required
@platform_staff_required
def ajax_destination_cities(request):
    country_id = request.GET.get("country_id")
    if not country_id:
        return JsonResponse([], safe=False)
    cities = (
        DestinationCity.objects.filter(country_id=country_id, is_active=True)
        .order_by("name")
        .values("id", "name")
    )
    return JsonResponse(list(cities), safe=False)


@login_required
@platform_staff_required
def ajax_destination_ports(request):
    city_id = request.GET.get("city_id")
    transport_mode = request.GET.get("transport_mode")
    if not city_id:
        return JsonResponse([], safe=False)

    ports = Port.objects.filter(city_id=city_id, is_active=True)

    if transport_mode == "air":
        ports = ports.filter(port_type="air")
    elif transport_mode in ["sea_fcl", "sea_lcl"]:
        ports = ports.filter(port_type="sea")
    elif transport_mode in ["land", "rail"]:
        ports = ports.filter(port_type__in=["land", "rail"])

    data = [
        {"id": p["id"], "name": f'{p["name"]} - {p["code"]}' if p["code"] else p["name"]}
        for p in ports.order_by("name").values("id", "name", "code")
    ]
    return JsonResponse(data, safe=False)


@login_required
@platform_staff_required
def ajax_cargo_types(request):
    transport_mode = request.GET.get("transport_mode")
    if not transport_mode:
        return JsonResponse([], safe=False)
    types = CargoType.objects.filter(transport_mode=transport_mode).order_by("name").values("id", "name")
    return JsonResponse(list(types), safe=False)
