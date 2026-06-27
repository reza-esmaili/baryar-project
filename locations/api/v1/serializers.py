from rest_framework import serializers
from locations.models import Province, City, Country, DestinationCity, Port


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["id", "name", "code"]


class ProvinceSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = Province
        fields = ["id", "name", "country", "country_name"]


class CitySerializer(serializers.ModelSerializer):
    province_name = serializers.CharField(source="province.name", read_only=True)
    country_id = serializers.IntegerField(source="province.country.id", read_only=True)

    class Meta:
        model = City
        fields = ["id", "name", "province", "province_name", "country_id"]


class DestinationCitySerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = DestinationCity
        fields = ["id", "name", "country", "country_name"]


class PortSerializer(serializers.ModelSerializer):
    transport_mode = serializers.CharField(source="port_type", read_only=True)
    port_type_display = serializers.CharField(source="get_port_type_display", read_only=True)
    country_id = serializers.IntegerField(source="city.country.id", read_only=True)
    country_name = serializers.CharField(source="city.country.name", read_only=True)
    city_name = serializers.CharField(source="city.name", read_only=True)

    class Meta:
        model = Port
        fields = [
            "id",
            "name",
            "code",
            "port_type",
            "port_type_display",
            "transport_mode",   # backward compatible
            "city",
            "city_name",
            "country_id",
            "country_name",
        ]
