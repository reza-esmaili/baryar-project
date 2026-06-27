from rest_framework import generics
from locations.models import Province, City, Country, DestinationCity, Port
from .serializers import (
    ProvinceSerializer,
    CitySerializer,
    CountrySerializer,
    DestinationCitySerializer,
    PortSerializer,
)


class CountryListAPIView(generics.ListAPIView):
    serializer_class = CountrySerializer

    def get_queryset(self):
        return Country.objects.filter(
            is_active=True
        ).order_by("name")


class ProvinceListAPIView(generics.ListAPIView):
    serializer_class = ProvinceSerializer

    def get_queryset(self):
        queryset = Province.objects.filter(
            is_active=True
        ).select_related("country").order_by("name")

        country_id = self.request.query_params.get("country_id")

        if country_id:
            queryset = queryset.filter(country_id=country_id)

        return queryset


class CityListAPIView(generics.ListAPIView):
    serializer_class = CitySerializer

    def get_queryset(self):
        queryset = (
            City.objects
            .filter(is_active=True)
            .select_related("province", "province__country")
            .order_by("name")
        )

        province_id = self.request.query_params.get("province_id")

        if province_id:
            queryset = queryset.filter(province_id=province_id)

        return queryset


class DestinationCityListAPIView(generics.ListAPIView):
    serializer_class = DestinationCitySerializer

    def get_queryset(self):
        queryset = (
            DestinationCity.objects
            .filter(is_active=True)
            .select_related("country")
            .order_by("name")
        )

        country_id = self.request.query_params.get("country_id")

        if country_id:
            queryset = queryset.filter(country_id=country_id)

        return queryset


class PortListAPIView(generics.ListAPIView):
    serializer_class = PortSerializer

    def get_queryset(self):
        queryset = (
            Port.objects
            .filter(is_active=True)
            .select_related("city", "city__country")
            .order_by("name")
        )

        country_id = self.request.query_params.get("country_id")
        city_id = self.request.query_params.get("city_id")
        transport_mode = self.request.query_params.get("transport_mode")

        if country_id:
            queryset = queryset.filter(city__country_id=country_id)

        if city_id:
            queryset = queryset.filter(city_id=city_id)

        # ✅ حفظ منطق AJAX قدیمی
        if transport_mode:
            if transport_mode == "air":
                queryset = queryset.filter(port_type="air")

            elif transport_mode in ["sea_fcl", "sea_lcl", "sea"]:
                queryset = queryset.filter(port_type="sea")

            elif transport_mode == "land":
                queryset = queryset.filter(port_type="land")

            elif transport_mode == "rail":
                queryset = queryset.filter(port_type="rail")

        return queryset
