from django.http import JsonResponse
from django.utils import timezone
from .models import Country, Province, City, DestinationCity, Port


def _active_rates():
    from rates.models import Rate
    return Rate.objects.filter(
        is_active=True,
        valid_until__gte=timezone.now().date()
    )


def _apply_origin_filter(rates, request):
    """اگر مبدا مشخص شده، نرخ‌ها را بر اساس آن فیلتر کن."""
    origin_city_id = request.GET.get("origin_city_id")
    origin_province_id = request.GET.get("origin_province_id")
    if origin_city_id:
        try:
            rates = rates.filter(origin_city_id=int(origin_city_id))
        except (ValueError, TypeError):
            pass
    elif origin_province_id:
        try:
            rates = rates.filter(origin_province_id=int(origin_province_id))
        except (ValueError, TypeError):
            pass
    return rates


def load_provinces(request):
    country_id = request.GET.get("country_id")
    provinces = Province.objects.none()
    if country_id:
        provinces = Province.objects.filter(
            country_id=country_id,
            is_active=True
        ).order_by("name")
    return JsonResponse(list(provinces.values("id", "name")), safe=False)


def load_cities(request):
    province_id = request.GET.get("province_id")
    cities = City.objects.none()
    if province_id:
        rated_city_ids = _active_rates().filter(
            origin_province_id=province_id
        ).values_list('origin_city_id', flat=True).distinct()
        cities = City.objects.filter(
            province_id=province_id,
            is_active=True,
            id__in=rated_city_ids
        ).order_by("name")
    return JsonResponse(list(cities.values("id", "name")), safe=False)


def load_countries_with_rates(request):
    """کشورهای مقصد که برای مبدا و روش حمل انتخابی نرخ فعال دارند."""
    transport_mode = request.GET.get("transport_mode")
    rates = _active_rates()
    if transport_mode:
        rates = rates.filter(transport_mode=transport_mode)
    rates = _apply_origin_filter(rates, request)
    country_ids = rates.values_list('destination_country_id', flat=True).distinct()
    countries = Country.objects.filter(
        is_active=True,
        id__in=country_ids
    ).order_by("name")
    return JsonResponse(list(countries.values("id", "name")), safe=False)


def load_destination_cities(request):
    country_id = request.GET.get("country_id")
    transport_mode = request.GET.get("transport_mode")
    dest_cities = DestinationCity.objects.none()
    if country_id:
        rates = _active_rates().filter(destination_country_id=country_id)
        if transport_mode:
            rates = rates.filter(transport_mode=transport_mode)
        rates = _apply_origin_filter(rates, request)
        rated_city_ids = rates.values_list('destination_city_id', flat=True).distinct()
        dest_cities = DestinationCity.objects.filter(
            country_id=country_id,
            is_active=True,
            id__in=rated_city_ids
        ).order_by("name")
    return JsonResponse(list(dest_cities.values("id", "name")), safe=False)


def load_ports(request):
    city_id = request.GET.get("city_id")
    transport_mode = request.GET.get("transport_mode")
    ports = Port.objects.none()
    if city_id:
        rates = _active_rates().filter(destination_city_id=city_id)
        if transport_mode:
            rates = rates.filter(transport_mode=transport_mode)
        rates = _apply_origin_filter(rates, request)
        rated_port_ids = rates.values_list('destination_port_id', flat=True).distinct()
        ports = Port.objects.filter(
            city_id=city_id,
            is_active=True,
            id__in=rated_port_ids
        )
        if transport_mode:
            if transport_mode == "air":
                ports = ports.filter(port_type="air")
            elif transport_mode in ["sea_fcl", "sea_lcl"]:
                ports = ports.filter(port_type="sea")
            elif transport_mode == "land":
                ports = ports.filter(port_type="land")
            elif transport_mode == "rail":
                ports = ports.filter(port_type="rail")
    return JsonResponse(list(ports.values("id", "name")), safe=False)
