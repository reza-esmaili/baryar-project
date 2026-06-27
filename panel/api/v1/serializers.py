from rest_framework import serializers

from orders.models import CargoRequest, OrderHistory, OrderStatus


class ForwarderOrderListSerializer(serializers.ModelSerializer):
    """
    Serializer لیست سفارشات فورواردر.

    نکته:
    tracking_code به صورت SerializerMethodField تعریف شده تا اگر در مدل وجود نداشت
    API کرش نکند و با نسخه‌های قبلی هم تا حد امکان سازگار بماند.
    """

    tracking_code = serializers.SerializerMethodField()

    customer_name = serializers.SerializerMethodField()
    customer_mobile = serializers.CharField(
        source="customer.mobile",
        read_only=True,
        allow_null=True
    )

    destination_port_name = serializers.CharField(
        source="destination_port.name",
        read_only=True,
        allow_null=True
    )

    destination_city_name = serializers.CharField(
        source="destination_port.city.name",
        read_only=True,
        allow_null=True
    )

    origin_city_name = serializers.CharField(
        source="origin_city.name",
        read_only=True,
        allow_null=True
    )

    cargo_type_name = serializers.CharField(
        source="cargo_type.name",
        read_only=True,
        allow_null=True
    )

    transport_mode_display = serializers.CharField(
        source="get_transport_mode_display",
        read_only=True
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True
    )

    selected_rate_id = serializers.IntegerField(
        source="selected_rate.id",
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = CargoRequest
        fields = [
            "id",
            "tracking_code",

            "customer_name",
            "customer_mobile",

            "sender_name",
            "sender_national_id",
            "sender_phone",

            "transport_mode",
            "transport_mode_display",

            "origin_city_name",

            "destination_port",
            "destination_port_name",
            "destination_city_name",

            "cargo_type",
            "cargo_type_name",

            "selected_rate_id",

            "status",
            "status_display",

            "actual_weight",
            "chargeable_weight",
            "final_price",

            "created_at",
            "updated_at",
        ]

        read_only_fields = fields

    def get_tracking_code(self, obj):
        """
        اگر پروژه قبلاً tracking_code داشته یا از property استفاده می‌کرده،
        مقدارش برگردانده می‌شود؛ اگر نه، یک مقدار امن بر اساس id می‌دهیم.
        """
        tracking_code = getattr(obj, "tracking_code", None)

        if tracking_code:
            return tracking_code

        return f"ORD-{obj.id}"

    def get_customer_name(self, obj):
        customer = getattr(obj, "customer", None)

        if not customer:
            return ""

        full_name = ""

        if hasattr(customer, "get_full_name"):
            full_name = customer.get_full_name()

        if full_name:
            return full_name

        first_name = getattr(customer, "first_name", "") or ""
        last_name = getattr(customer, "last_name", "") or ""

        name = f"{first_name} {last_name}".strip()

        if name:
            return name

        return getattr(customer, "mobile", "") or str(customer)


class ForwarderOrderDetailSerializer(ForwarderOrderListSerializer):
    """
    Serializer کامل‌تر برای جزئیات سفارش.
    فعلاً در URLهای فعلی استفاده نشده، اما برای توسعه بعدی API آماده است.
    """

    cargo_subcategories = serializers.SerializerMethodField()
    dimensions = serializers.SerializerMethodField()

    class Meta(ForwarderOrderListSerializer.Meta):
        fields = ForwarderOrderListSerializer.Meta.fields + [
            "origin_country",
            "origin_province",
            "origin_city",

            "shipping_procedure",
            "container_size",
            "container_type",
            "container_count",

            "base_shipping_price",
            "office_packaging_price",
            "onsite_packaging_price",
            "doorstep_packaging_price",
            "vat_amount",
            "price_subtotal",

            "needs_office_packaging",
            "needs_onsite_packaging",
            "needs_doorstep_packaging",

            "cargo_subcategories",
            "other_cargo_details",

            "sender_province",
            "sender_city",
            "sender_address",

            "dimensions",
        ]

        read_only_fields = fields

    def get_cargo_subcategories(self, obj):
        return [
            {
                "id": item.id,
                "name": item.name,
            }
            for item in obj.cargo_subcategories.all()
        ]

    def get_dimensions(self, obj):
        return [
            {
                "id": dim.id,
                "length": dim.length,
                "width": dim.width,
                "height": dim.height,
                "quantity": dim.quantity,
                "volume_cm3": dim.volume_cm3,
            }
            for dim in obj.dimensions.all()
        ]


class ForwarderOrderStatusUpdateSerializer(serializers.Serializer):
    """
    تغییر وضعیت سفارش توسط فورواردر.

    choices مستقیماً از OrderStatus خوانده می‌شود تا دیگر لازم نباشد
    داخل view به صورت دستی مقداردهی شود.
    """

    status = serializers.ChoiceField(
        choices=OrderStatus.choices
    )

    note = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )


class ForwarderDashboardSerializer(serializers.Serializer):
    """
    Serializer خروجی داشبورد.

    این serializer بیشتر برای مستندسازی ساختار خروجی است و اجباری نیست،
    اما نگه داشتنش برای Swagger / drf-spectacular مفید است.
    """

    total_orders_count = serializers.IntegerField()
    total_sales = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_active_rates = serializers.IntegerField()

    top_transport_mode = serializers.DictField(allow_null=True)
    top_destination = serializers.DictField(allow_null=True)

    rates_by_route = serializers.ListField()
    sales_chart = serializers.DictField()
