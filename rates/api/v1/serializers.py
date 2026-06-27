from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError

from rates.models import (
    Rate,
    RateTier,
    CargoType,
    CargoSubCategory,
)

from locations.models import City, DestinationCity, Port


class CargoSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CargoSubCategory
        fields = [
            "id",
            "name",
            "description",
        ]


class CargoTypeSerializer(serializers.ModelSerializer):
    subcategories = CargoSubCategorySerializer(
        many=True,
        read_only=True
    )

    transport_mode_display = serializers.CharField(
        source="get_transport_mode_display",
        read_only=True
    )

    class Meta:
        model = CargoType
        fields = [
            "id",
            "name",
            "transport_mode",
            "transport_mode_display",
            "subcategories",
        ]


class RateTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = RateTier
        fields = [
            "id",
            "pricing_unit",
            "price",
            "weight_from",
            "weight_to",
            "container_size",
            "container_type",
        ]

    def validate(self, data):
        # اعتبارسنجی کامل در مدل انجام می‌شود
        return data


class RateSerializer(serializers.ModelSerializer):

    tiers = RateTierSerializer(many=True)

    cargo_types = serializers.PrimaryKeyRelatedField(
        queryset=CargoType.objects.all(),
        many=True,
        required=False
    )

    is_currently_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Rate

        fields = [

            "id",

            "forwarder",
            "branch",

            "shipping_procedure",

            "transport_mode",

            "origin_country",
            "origin_province",
            "origin_city",

            "cargo_types",

            "destination_country",
            "destination_city",
            "destination_port",

            "is_active",
            "valid_until",

            "onsite_packaging_charge_type",
            "onsite_packaging_price",

            "office_packaging_charge_type",
            "office_packaging_price",

            "doorstep_packaging_charge_type",
            "doorstep_packaging_price",

            "add_vat",

            "created_at",
            "updated_at",

            "is_currently_active",

            "tiers",
        ]

        read_only_fields = [
            "created_at",
            "updated_at",
            "is_currently_active",
        ]

    def validate(self, data):

        tiers_data = self.initial_data.get("tiers", [])

        # ساخت نمونه موقت برای اجرای clean مدل
        instance = Rate(**data)

        try:
            instance.clean()

        except DjangoValidationError as e:

            if hasattr(e, "message_dict"):
                raise serializers.ValidationError(e.message_dict)

            raise serializers.ValidationError(e.messages)

        # اعتبارسنجی tier ها
        for tier_data in tiers_data:

            tier = RateTier(
                rate=instance,
                **tier_data
            )

            try:
                tier.clean()

            except DjangoValidationError as e:

                if hasattr(e, "message_dict"):
                    raise serializers.ValidationError(e.message_dict)

                raise serializers.ValidationError(e.messages)

        return data

    def create(self, validated_data):

        tiers_data = validated_data.pop("tiers", [])

        cargo_types = validated_data.pop("cargo_types", [])

        rate = Rate.objects.create(**validated_data)

        if cargo_types:
            rate.cargo_types.set(cargo_types)

        for tier_data in tiers_data:

            tier = RateTier(
                rate=rate,
                **tier_data
            )

            tier.clean()
            tier.save()

        return rate

    def update(self, instance, validated_data):

        tiers_data = validated_data.pop("tiers", None)

        cargo_types = validated_data.pop("cargo_types", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if cargo_types is not None:
            instance.cargo_types.set(cargo_types)

        if tiers_data is not None:

            instance.tiers.all().delete()

            for tier_data in tiers_data:

                tier = RateTier(
                    rate=instance,
                    **tier_data
                )

                tier.clean()
                tier.save()

        return instance
