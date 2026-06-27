from decimal import Decimal

from rest_framework import serializers
from django.db import transaction
from django.shortcuts import get_object_or_404

from orders.models import CargoRequest, CargoDimension, OrderHistory, OrderStatus
from orders.services import calculate_and_match_rates, calculate_extra_charge, money

from locations.models import Country, Province, City, Port
from rates.models import (
    Rate,
    CargoType,
    CargoSubCategory,
    ExtraChargeType,
)
from core.choices import ShippingProcedure


class CargoDimensionSerializer(serializers.ModelSerializer):
    volume_cm3 = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = CargoDimension
        fields = [
            'id',
            'length',
            'width',
            'height',
            'quantity',
            'volume_cm3',
        ]
        read_only_fields = ['id', 'volume_cm3']


class CargoRequestSerializer(serializers.ModelSerializer):
    """
    سریالایزر اصلی سفارش حمل.

    نکات:
    - ابعاد به صورت nested دریافت و ذخیره می‌شوند.
    - قیمت‌ها و وضعیت سفارش از سمت کلاینت قابل اعتماد نیستند و read-only هستند.
    - اگر selected_rate ارسال شود، نرخ در سرور مجدداً محاسبه و اعتبارسنجی می‌شود.
    """

    dimensions = CargoDimensionSerializer(many=True, required=False)

    cargo_subcategories = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=CargoSubCategory.objects.all()
    )

    customer = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = CargoRequest
        fields = [
            'id',
            'customer',

            # مسیر و مشخصات اصلی
            'origin_country',
            'origin_province',
            'origin_city',
            'destination_port',
            'transport_mode',
            'shipping_procedure',
            'cargo_type',

            # وزن‌ها
            'actual_weight',
            'chargeable_weight',

            # کانتینر FCL
            'container_size',
            'container_type',
            'container_count',

            # نرخ انتخابی
            'selected_rate',

            # قیمت‌ها
            'base_shipping_price',
            'office_packaging_price',
            'onsite_packaging_price',
            'doorstep_packaging_price',
            'vat_amount',
            'price_subtotal',
            'final_price',

            # گزینه‌های بسته‌بندی
            'needs_office_packaging',
            'needs_onsite_packaging',
            'needs_doorstep_packaging',

            # وضعیت
            'status',

            # جزئیات کالا
            'cargo_subcategories',
            'other_cargo_details',

            # اطلاعات فرستنده
            'sender_name',
            'sender_national_id',
            'sender_phone',
            'sender_province',
            'sender_city',
            'sender_address',

            # ابعاد
            'dimensions',

            # فیلدهای timestamp در صورتی که TimeStampedModel داشته باشد
            'created_at',
            'updated_at',
        ]

        read_only_fields = [
            'id',
            'customer',
            'status',
            'chargeable_weight',

            'base_shipping_price',
            'office_packaging_price',
            'onsite_packaging_price',
            'doorstep_packaging_price',
            'vat_amount',
            'price_subtotal',
            'final_price',

            'created_at',
            'updated_at',
        ]

    def validate(self, data):
        """
        اعتبارسنجی عمومی سفارش:
        - کنترل سازگاری کشور/استان/شهر مبدا
        - کنترل FCL و غیر FCL
        - کنترل selected_rate در صورت ارسال
        """

        instance = self.instance

        transport_mode = data.get(
            'transport_mode',
            getattr(instance, 'transport_mode', None)
        )

        origin_country = data.get(
            'origin_country',
            getattr(instance, 'origin_country', None)
        )

        origin_province = data.get(
            'origin_province',
            getattr(instance, 'origin_province', None)
        )

        origin_city = data.get(
            'origin_city',
            getattr(instance, 'origin_city', None)
        )

        selected_rate = data.get(
            'selected_rate',
            getattr(instance, 'selected_rate', None)
        )

        shipping_procedure = data.get(
            'shipping_procedure',
            getattr(instance, 'shipping_procedure', None)
        )

        dimensions = data.get('dimensions', None)

        # اعتبارسنجی کشور/استان/شهر
        if origin_country and origin_province:
            if origin_province.country_id != origin_country.id:
                raise serializers.ValidationError({
                    'origin_province': 'استان مبدا متعلق به کشور انتخاب‌شده نیست.'
                })

        if origin_province and origin_city:
            if origin_city.province_id != origin_province.id:
                raise serializers.ValidationError({
                    'origin_city': 'شهر مبدا متعلق به استان انتخاب‌شده نیست.'
                })

        # بررسی FCL
        is_fcl = transport_mode in ['sea_fcl', 'FCL']

        if is_fcl:
            container_size = data.get(
                'container_size',
                getattr(instance, 'container_size', None)
            )
            container_type = data.get(
                'container_type',
                getattr(instance, 'container_type', None)
            )
            container_count = data.get(
                'container_count',
                getattr(instance, 'container_count', None)
            )

            if not container_size or not container_type or not container_count:
                raise serializers.ValidationError(
                    'برای حمل FCL، سایز کانتینر، نوع کانتینر و تعداد کانتینر الزامی است.'
                )

        else:
            # در create برای غیر FCL ابعاد لازم است.
            # در update اگر dimensions ارسال نشود، ابعاد قبلی حفظ می‌شوند.
            if instance is None and not dimensions:
                raise serializers.ValidationError(
                    'برای این نوع حمل، وارد کردن حداقل یک ردیف ابعاد کالا الزامی است.'
                )

        # اعتبارسنجی نرخ انتخاب‌شده
        if selected_rate:
            if transport_mode and selected_rate.transport_mode != transport_mode:
                raise serializers.ValidationError({
                    'selected_rate': 'نرخ انتخاب‌شده با روش حمل سفارش مطابقت ندارد.'
                })

            if shipping_procedure and selected_rate.shipping_procedure != shipping_procedure:
                raise serializers.ValidationError({
                    'selected_rate': 'نرخ انتخاب‌شده با رویه ارسال سفارش مطابقت ندارد.'
                })

        return data

    def _build_calculation_payload(self, data, instance=None):
        """
        ساخت payload سازگار با سرویس calculate_and_match_rates.

        این سرویس در وب از form.cleaned_data استفاده می‌کند.
        اینجا سعی می‌کنیم همان ساختار را برای API بسازیم.
        """

        def get_value(field_name, default=None):
            if field_name in data:
                return data.get(field_name)
            if instance is not None:
                return getattr(instance, field_name, default)
            return default

        payload = {
            'origin_country': get_value('origin_country'),
            'origin_province': get_value('origin_province'),
            'origin_city': get_value('origin_city'),
            'destination_port': get_value('destination_port'),
            'transport_mode': get_value('transport_mode'),
            'shipping_procedure': get_value('shipping_procedure'),
            'cargo_type': get_value('cargo_type'),
            'actual_weight': get_value('actual_weight'),

            'container_size': get_value('container_size'),
            'container_type': get_value('container_type'),
            'container_count': get_value('container_count'),

            'needs_office_packaging': get_value('needs_office_packaging', False),
            'needs_onsite_packaging': get_value('needs_onsite_packaging', False),
            'needs_doorstep_packaging': get_value('needs_doorstep_packaging', False),

            'other_cargo_details': get_value('other_cargo_details'),
        }

        cargo_subcategories = data.get('cargo_subcategories', None)

        if cargo_subcategories is not None:
            payload['cargo_subcategories'] = cargo_subcategories
        elif instance is not None:
            payload['cargo_subcategories'] = list(instance.cargo_subcategories.all())
        else:
            payload['cargo_subcategories'] = []

        return payload

    def _apply_selected_rate_pricing(self, cargo_request, selected_rate, calculation_payload, dimensions_data):
        """
        محاسبه مجدد نرخ در سرور و اعمال breakdown قیمت روی سفارش.
        """

        is_fcl = calculation_payload.get('transport_mode') in ['sea_fcl', 'FCL']
        service_dimensions = [] if is_fcl else dimensions_data

        match_data = calculate_and_match_rates(
            calculation_payload,
            service_dimensions
        )

        selected_result = None

        for item in match_data.get('results', []):
            if str(item.get('rate_id')) == str(selected_rate.id):
                selected_result = item
                break

        if not selected_result:
            raise serializers.ValidationError({
                'selected_rate': 'نرخ انتخاب‌شده معتبر نیست یا منقضی شده است.'
            })

        cargo_request.selected_rate = selected_rate
        cargo_request.chargeable_weight = match_data.get('chargeable_weight', 0)

        cargo_request.base_shipping_price = selected_result.get('base_shipping_price', 0)
        cargo_request.office_packaging_price = selected_result.get('office_packaging_price', 0)
        cargo_request.onsite_packaging_price = selected_result.get('onsite_packaging_price', 0)
        cargo_request.doorstep_packaging_price = selected_result.get('doorstep_packaging_price', 0)
        cargo_request.vat_amount = selected_result.get('vat_amount', 0)
        cargo_request.price_subtotal = selected_result.get('subtotal', 0)
        cargo_request.final_price = selected_result.get('total_price', 0)

        return cargo_request

    @transaction.atomic
    def create(self, validated_data):
        dimensions_data = validated_data.pop('dimensions', [])
        cargo_subcategories = validated_data.pop('cargo_subcategories', [])
        selected_rate = validated_data.get('selected_rate', None)

        request = self.context.get('request')

        if request and hasattr(request, 'user'):
            validated_data['customer'] = request.user

        # سفارش در API نیز در ابتدا پیش‌نویس باشد
        validated_data['status'] = OrderStatus.DRAFT

        calculation_payload = self._build_calculation_payload(validated_data)

        cargo_request = CargoRequest(**validated_data)

        # اگر نرخ انتخاب شده، قیمت‌ها از سمت سرور محاسبه شود
        if selected_rate:
            cargo_request = self._apply_selected_rate_pricing(
                cargo_request=cargo_request,
                selected_rate=selected_rate,
                calculation_payload=calculation_payload,
                dimensions_data=dimensions_data
            )

        cargo_request.save()

        if cargo_subcategories:
            cargo_request.cargo_subcategories.set(cargo_subcategories)

        is_fcl = cargo_request.transport_mode in ['sea_fcl', 'FCL']

        if not is_fcl:
            for dim_data in dimensions_data:
                CargoDimension.objects.create(
                    cargo_request=cargo_request,
                    **dim_data
                )

        OrderHistory.objects.create(
            order=cargo_request,
            changed_by=request.user if request else None,
            note='سفارش از طریق API ثبت شد.'
        )

        return cargo_request

    @transaction.atomic
    def update(self, instance, validated_data):
        dimensions_data = validated_data.pop('dimensions', None)
        cargo_subcategories = validated_data.pop('cargo_subcategories', None)
        selected_rate = validated_data.get('selected_rate', instance.selected_rate)

        old_status = instance.status

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if cargo_subcategories is not None:
            # بعد از save ست می‌شود
            pass

        # اگر نرخ انتخابی وجود دارد، محاسبه دوباره انجام شود.
        # برای update اگر dimensions ارسال نشده بود، ابعاد قبلی استفاده می‌شوند.
        if selected_rate:
            if dimensions_data is None:
                dimensions_for_calc = [
                    {
                        'length': dim.length,
                        'width': dim.width,
                        'height': dim.height,
                        'quantity': dim.quantity,
                    }
                    for dim in instance.dimensions.all()
                ]
            else:
                dimensions_for_calc = dimensions_data

            calculation_payload = self._build_calculation_payload(
                validated_data,
                instance=instance
            )

            instance = self._apply_selected_rate_pricing(
                cargo_request=instance,
                selected_rate=selected_rate,
                calculation_payload=calculation_payload,
                dimensions_data=dimensions_for_calc
            )

        instance.save()

        if cargo_subcategories is not None:
            instance.cargo_subcategories.set(cargo_subcategories)

        if dimensions_data is not None:
            instance.dimensions.all().delete()

            is_fcl = instance.transport_mode in ['sea_fcl', 'FCL']

            if not is_fcl:
                for dim_data in dimensions_data:
                    CargoDimension.objects.create(
                        cargo_request=instance,
                        **dim_data
                    )

        request = self.context.get('request')

        OrderHistory.objects.create(
            order=instance,
            changed_by=request.user if request else None,
            note='سفارش از طریق API ویرایش شد.'
        )

        if old_status != instance.status:
            OrderHistory.objects.create(
                order=instance,
                changed_by=request.user if request else None,
                field_name='status',
                old_value=old_status,
                new_value=instance.status,
                note='وضعیت سفارش تغییر کرد.'
            )

        return instance


class OrderHistorySerializer(serializers.ModelSerializer):
    changed_by_display = serializers.StringRelatedField(
        source='changed_by',
        read_only=True
    )

    class Meta:
        model = OrderHistory
        fields = [
            'id',
            'order',
            'changed_by',
            'changed_by_display',
            'field_name',
            'old_value',
            'new_value',
            'note',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class RateDimensionSerializer(serializers.Serializer):
    """
    سریالایزر ابعاد کالا برای محاسبه نرخ بدون ذخیره در دیتابیس.
    """

    length = serializers.DecimalField(max_digits=8, decimal_places=2)
    width = serializers.DecimalField(max_digits=8, decimal_places=2)
    height = serializers.DecimalField(max_digits=8, decimal_places=2)
    quantity = serializers.IntegerField(default=1, min_value=1)


class RateCalculationRequestSerializer(serializers.Serializer):
    """
    سریالایزر استعلام نرخ.

    ورودی جدید پیشنهادی:
    - origin_city
    - destination_port
    - actual_weight

    برای جلوگیری از خراب شدن منطق قبلی، این ورودی‌های قدیمی هم پشتیبانی می‌شوند:
    - origin_id -> origin_city
    - destination_id -> destination_port
    - gross_weight -> actual_weight
    """

    # فیلدهای جدید
    origin_country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        required=False,
        allow_null=True
    )

    origin_province = serializers.PrimaryKeyRelatedField(
        queryset=Province.objects.all(),
        required=False,
        allow_null=True
    )

    origin_city = serializers.PrimaryKeyRelatedField(
        queryset=City.objects.all(),
        required=False
    )

    destination_port = serializers.PrimaryKeyRelatedField(
        queryset=Port.objects.all(),
        required=False
    )

    transport_mode = serializers.CharField(max_length=50)

    shipping_procedure = serializers.ChoiceField(
        choices=ShippingProcedure.choices,
        required=False,
        default=ShippingProcedure.COMMERCIAL
    )

    cargo_type = serializers.PrimaryKeyRelatedField(
        queryset=CargoType.objects.all()
    )

    actual_weight = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False
    )

    # فیلدهای قدیمی برای backward compatibility
    origin_id = serializers.IntegerField(required=False, write_only=True)
    destination_id = serializers.IntegerField(required=False, write_only=True)
    gross_weight = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        write_only=True
    )

    # FCL
    container_size = serializers.CharField(max_length=20, required=False)
    container_type = serializers.CharField(max_length=50, required=False)
    container_count = serializers.IntegerField(required=False, min_value=1)

    # امکانات بسته‌بندی
    needs_office_packaging = serializers.BooleanField(required=False, default=False)
    needs_onsite_packaging = serializers.BooleanField(required=False, default=False)
    needs_doorstep_packaging = serializers.BooleanField(required=False, default=False)

    # جزئیات کالا
    cargo_subcategories = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CargoSubCategory.objects.all(),
        required=False
    )

    other_cargo_details = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        allow_null=True
    )

    # ابعاد برای غیر FCL
    dimensions = RateDimensionSerializer(many=True, required=False)

    def validate(self, data):
        transport_mode = data.get('transport_mode')
        is_fcl = transport_mode in ['sea_fcl', 'FCL']

        # پشتیبانی از origin_id قدیمی
        origin_id = data.pop('origin_id', None)

        if not data.get('origin_city') and origin_id:
            try:
                data['origin_city'] = City.objects.get(id=origin_id)
            except City.DoesNotExist:
                raise serializers.ValidationError({
                    'origin_id': 'شهر مبدا با این شناسه پیدا نشد.'
                })

        # پشتیبانی از destination_id قدیمی
        destination_id = data.pop('destination_id', None)

        if not data.get('destination_port') and destination_id:
            try:
                data['destination_port'] = Port.objects.get(id=destination_id)
            except Port.DoesNotExist:
                raise serializers.ValidationError({
                    'destination_id': 'پورت/فرودگاه مقصد با این شناسه پیدا نشد.'
                })

        # پشتیبانی از gross_weight قدیمی
        gross_weight = data.pop('gross_weight', None)

        if not data.get('actual_weight') and gross_weight is not None:
            data['actual_weight'] = gross_weight

        if not data.get('origin_city'):
            raise serializers.ValidationError({
                'origin_city': 'شهر مبدا الزامی است.'
            })

        if not data.get('destination_port'):
            raise serializers.ValidationError({
                'destination_port': 'پورت/فرودگاه مقصد الزامی است.'
            })

        # اگر کشور/استان ارسال نشده باشد، از روی شهر مبدا تکمیل می‌کنیم
        origin_city = data.get('origin_city')

        if origin_city:
            if not data.get('origin_province'):
                data['origin_province'] = origin_city.province

            if not data.get('origin_country') and origin_city.province:
                data['origin_country'] = origin_city.province.country

        origin_country = data.get('origin_country')
        origin_province = data.get('origin_province')

        if origin_country and origin_province:
            if origin_province.country_id != origin_country.id:
                raise serializers.ValidationError({
                    'origin_province': 'استان مبدا متعلق به کشور انتخاب‌شده نیست.'
                })

        if origin_province and origin_city:
            if origin_city.province_id != origin_province.id:
                raise serializers.ValidationError({
                    'origin_city': 'شهر مبدا متعلق به استان انتخاب‌شده نیست.'
                })

        if is_fcl:
            if not data.get('container_size'):
                raise serializers.ValidationError({
                    'container_size': 'برای حمل FCL، سایز کانتینر الزامی است.'
                })

            if not data.get('container_type'):
                raise serializers.ValidationError({
                    'container_type': 'برای حمل FCL، نوع کانتینر الزامی است.'
                })

            if not data.get('container_count'):
                raise serializers.ValidationError({
                    'container_count': 'برای حمل FCL، تعداد کانتینر الزامی است.'
                })

            # برای FCL ابعاد لازم نیست
            data['dimensions'] = []

        else:
            if not data.get('actual_weight'):
                raise serializers.ValidationError({
                    'actual_weight': 'برای این نوع حمل، وزن واقعی الزامی است.'
                })

            if not data.get('dimensions'):
                raise serializers.ValidationError({
                    'dimensions': 'برای این نوع حمل، وارد کردن حداقل یک ردیف ابعاد کالا الزامی است.'
                })

        return data
