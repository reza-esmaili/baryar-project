from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from rates.models import RateTier, ExtraChargeType


VAT_RATE = Decimal("0.10")


def money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_extra_charge(charge_type, unit_price, weight):
    unit_price = Decimal(str(unit_price or 0))
    weight = Decimal(str(weight or 0))

    if charge_type == ExtraChargeType.NOT_AVAILABLE:
        return Decimal("0.00")

    if charge_type == ExtraChargeType.FREE:
        return Decimal("0.00")

    if charge_type == ExtraChargeType.FIXED:
        return unit_price

    if charge_type == ExtraChargeType.PER_KG:
        return unit_price * weight

    return Decimal("0.00")


def calculate_and_match_rates(data, dimensions_data):
    transport_mode = data.get('transport_mode')
    shipping_procedure = data.get('shipping_procedure')
    is_fcl = transport_mode in ['sea_fcl', 'FCL']

    # فیلدهای جدید انتخاب سرویس‌های بسته‌بندی
    needs_office_packaging = bool(data.get('needs_office_packaging'))
    needs_onsite_packaging = bool(data.get('needs_onsite_packaging'))
    needs_doorstep_packaging = bool(data.get('needs_doorstep_packaging'))

    # 1. محاسبه وزن حجمی
    total_volumetric_weight = Decimal('0.0')

    if not is_fcl and dimensions_data:
        divisor = Decimal('6000')

        for dim in dimensions_data:
            if dim and not dim.get('DELETE', False) and dim.get('length'):
                volume = (
                    Decimal(str(dim['length'])) *
                    Decimal(str(dim['width'])) *
                    Decimal(str(dim['height'])) *
                    Decimal(str(dim['quantity']))
                )
                total_volumetric_weight += volume / divisor

    # 2. تعیین Chargeable Weight
    weight_val = data.get('gross_weight') or data.get('actual_weight') or '0.0'
    actual_wt = Decimal(str(weight_val))
    cw = max(actual_wt, total_volumetric_weight)

    # 3. ساخت فیلترهای پایه برای جستجوی نرخ‌ها
    query_filters = {
        'rate__is_active': True,
        'rate__valid_until__gte': timezone.now().date(),
        'rate__transport_mode': transport_mode,
    }

    if shipping_procedure:
        query_filters['rate__shipping_procedure'] = shipping_procedure

    # کشور مبدا
    if data.get('origin_country'):
        query_filters['rate__origin_country_id'] = data.get('origin_country')

    # استان مبدا
    if data.get('origin_province'):
        query_filters['rate__origin_province_id'] = data.get('origin_province')

    # شهر مبدا
    if data.get('origin_id'):
        query_filters['rate__origin_city_id'] = data.get('origin_id')
    elif data.get('origin_city'):
        query_filters['rate__origin_city'] = data.get('origin_city')

    # مقصد
    if data.get('destination_id'):
        query_filters['rate__destination_port_id'] = data.get('destination_id')
    elif data.get('destination_port'):
        query_filters['rate__destination_port'] = data.get('destination_port')

    # نوع کالا
    if data.get('cargo_type'):
        query_filters['rate__cargo_types'] = data.get('cargo_type')

    base_query = RateTier.objects.filter(**query_filters).select_related(
        'rate',
        'rate__forwarder',
        'rate__branch',
        'rate__branch__company'
    ).distinct()

    if is_fcl:
        fcl_filters = {
            'container_size': data.get('container_size')
        }

        if data.get('container_type'):
            fcl_filters['container_type'] = data.get('container_type')

        valid_tiers = base_query.filter(**fcl_filters)
    else:
        valid_tiers = base_query.filter(
            weight_from__lte=cw,
            weight_to__gte=cw
        )

    results = []

    for tier in valid_tiers:
        rate = tier.rate

        # محاسبه نرخ حمل
        if is_fcl:
            count = int(data.get('container_count') or 1)
            base_shipping_price = Decimal(str(tier.price)) * count
            extra_charge_weight = actual_wt
        else:
            if tier.pricing_unit == 'per_kg':
                base_shipping_price = Decimal(str(tier.price)) * cw
            else:
                base_shipping_price = Decimal(str(tier.price))

            extra_charge_weight = cw

        # اگر مشتری بسته‌بندی در دفتر را انتخاب کرده باشد،
        # فقط نرخ‌هایی معتبرند که این سرویس را ارائه می‌کنند.
        if (
            needs_office_packaging and
            rate.office_packaging_charge_type == ExtraChargeType.NOT_AVAILABLE
        ):
            continue

        # اگر مشتری بسته‌بندی در محل را انتخاب کرده باشد،
        # فقط نرخ‌هایی معتبرند که این سرویس را ارائه می‌کنند.
        if (
            needs_onsite_packaging and
            rate.onsite_packaging_charge_type == ExtraChargeType.NOT_AVAILABLE
        ):
            continue

        # اگر مشتری بسته‌بندی و تحویل در محل را انتخاب کرده باشد،
        # فقط نرخ‌هایی معتبرند که این سرویس را ارائه می‌کنند.
        if (
            needs_doorstep_packaging and
            rate.doorstep_packaging_charge_type == ExtraChargeType.NOT_AVAILABLE
        ):
            continue

        # هزینه بسته‌بندی در دفتر فقط در صورت انتخاب مشتری لحاظ شود
        if needs_office_packaging:
            office_packaging_price = calculate_extra_charge(
                rate.office_packaging_charge_type,
                rate.office_packaging_price,
                extra_charge_weight
            )
        else:
            office_packaging_price = Decimal("0.00")

        # هزینه بسته‌بندی در محل فقط در صورت انتخاب مشتری لحاظ شود
        if needs_onsite_packaging:
            onsite_packaging_price = calculate_extra_charge(
                rate.onsite_packaging_charge_type,
                rate.onsite_packaging_price,
                extra_charge_weight
            )
        else:
            onsite_packaging_price = Decimal("0.00")

        # هزینه بسته‌بندی و تحویل در محل فقط در صورت انتخاب مشتری لحاظ شود
        if needs_doorstep_packaging:
            doorstep_packaging_price = calculate_extra_charge(
                rate.doorstep_packaging_charge_type,
                rate.doorstep_packaging_price,
                extra_charge_weight
            )
        else:
            doorstep_packaging_price = Decimal("0.00")

        subtotal = (
            base_shipping_price +
            office_packaging_price +
            onsite_packaging_price +
            doorstep_packaging_price
        )

        if rate.add_vat:
            vat_amount = subtotal * VAT_RATE
        else:
            vat_amount = Decimal("0.00")

        total_price = subtotal + vat_amount

        if rate.forwarder:
            company_name = rate.forwarder.company_name
            company_logo = rate.forwarder.logo.url if rate.forwarder.logo else None
        elif hasattr(rate, 'branch') and rate.branch:
            company_name = rate.branch.company.company_name
            company_logo = rate.branch.company.logo.url if rate.branch.company.logo else None
        else:
            company_name = "ناشناس"
            company_logo = None

        results.append({
            'rate_id': rate.id,
            'company_name': company_name,
            'company_logo': company_logo,

            'unit_price': str(money(tier.price)),

            'base_shipping_price': str(money(base_shipping_price)),

            # بسته‌بندی در دفتر
            'needs_office_packaging': needs_office_packaging,
            'office_packaging_available': (
                rate.office_packaging_charge_type != ExtraChargeType.NOT_AVAILABLE
            ),
            'office_packaging_charge_type': rate.office_packaging_charge_type,
            'office_packaging_unit_price': str(money(rate.office_packaging_price)),
            'office_packaging_price': str(money(office_packaging_price)),

            # بسته‌بندی در محل
            'needs_onsite_packaging': needs_onsite_packaging,
            'onsite_packaging_available': (
                rate.onsite_packaging_charge_type != ExtraChargeType.NOT_AVAILABLE
            ),
            'onsite_packaging_charge_type': rate.onsite_packaging_charge_type,
            'onsite_packaging_unit_price': str(money(rate.onsite_packaging_price)),
            'onsite_packaging_price': str(money(onsite_packaging_price)),

            # بسته‌بندی و تحویل در محل
            'needs_doorstep_packaging': needs_doorstep_packaging,
            'doorstep_packaging_available': (
                rate.doorstep_packaging_charge_type != ExtraChargeType.NOT_AVAILABLE
            ),
            'doorstep_packaging_charge_type': rate.doorstep_packaging_charge_type,
            'doorstep_packaging_unit_price': str(money(rate.doorstep_packaging_price)),
            'doorstep_packaging_price': str(money(doorstep_packaging_price)),

            'add_vat': rate.add_vat,
            'vat_amount': str(money(vat_amount)),

            'subtotal': str(money(subtotal)),
            'total_price': str(money(total_price)),

            'shipping_procedure': rate.shipping_procedure,
        })

    results = sorted(results, key=lambda x: Decimal(x['total_price']))

    return {
        'actual_weight': str(money(actual_wt)),
        'volumetric_weight': str(money(total_volumetric_weight)),
        'chargeable_weight': str(money(cw)),
        'results': results
    }


def get_forwarder_notification_target(rate):
    """
    از یک Rate، شماره موبایل و نام قابل‌نمایش «صاحب نرخ» را برمی‌گرداند تا
    بتوان به او اطلاع‌رسانی (پیامک/اعلان) کرد. rate.forwarder و rate.branch
    متقابلاً انحصاری‌اند (Rate.clean())؛ اگر نرخ متعلق به یک شعبه باشد،
    گیرنده کاربر همان شعبه (branch_user) است، نه ادمین کل شرکت.

    خروجی: (mobile, company_name) یا (None, None) اگر چیزی پیدا نشود.
    """
    if rate.forwarder_id:
        forwarder = rate.forwarder
        admin_user = forwarder.admin_user
        mobile = admin_user.mobile if admin_user else None
        return mobile, forwarder.company_name

    if rate.branch_id:
        branch = rate.branch
        branch_user = branch.branch_user
        mobile = branch_user.mobile if branch_user else None
        return mobile, branch.company.company_name

    return None, None
