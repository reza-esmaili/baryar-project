from datetime import timedelta

import jdatetime
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncQuarter, TruncWeek, TruncYear
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from orders.models import CargoRequest, OrderStatus
from rates.models import Rate, TransportMode

from .decorators import forwarder_required, get_company_for_user, staff_permission_required


@login_required
@forwarder_required
def dashboard_view(request):
    forwarder_company = get_company_for_user(request.user)

    context = cache.get(f'panel_dashboard:{forwarder_company.id}') if forwarder_company else None

    if context is None:
        # تاریخ ۷ روز پیش
        seven_days_ago = timezone.now() - timedelta(days=7)

        # فیلتر سفارشات مرتبط با این فورواردر در ۷ روز گذشته (بدون در نظر گرفتن پیش‌نویس‌ها)
        recent_orders = CargoRequest.objects.filter(
            selected_rate__forwarder=forwarder_company,
            created_at__gte=seven_days_ago
        ).exclude(status=OrderStatus.DRAFT)

        # 1. تعداد کل سفارشات و مبلغ فروش در 7 روز گذشته
        total_orders_count = recent_orders.count()
        total_sales = recent_orders.aggregate(total=Sum('final_price'))['total'] or 0
        avg_order_amount = recent_orders.aggregate(avg=Avg('final_price'))['avg'] or 0

        # 2. تعداد سفارشات در انتظار تایید (کل، نه فقط هفته اخیر)
        pending_payment_count = CargoRequest.objects.filter(
            selected_rate__forwarder=forwarder_company,
            status=OrderStatus.PENDING,
        ).count()

        # 3. تعداد مقصدهای فعال (unique destination ports در سفارشات غیر draft)
        active_destinations_count = CargoRequest.objects.filter(
            selected_rate__forwarder=forwarder_company,
        ).exclude(status=OrderStatus.DRAFT).values('destination_port').distinct().count()

        # 4. پرفروش‌ترین روش حمل در 7 روز گذشته
        top_transport_mode = recent_orders.values('transport_mode').annotate(
            order_count=Count('id'),
            total_sales=Sum('final_price')
        ).order_by('-order_count').first()

        mode_choices = dict(TransportMode.choices)
        if top_transport_mode:
            top_transport_mode['display_name'] = mode_choices.get(top_transport_mode['transport_mode'], top_transport_mode['transport_mode'])

        # 5. پرتردد‌ترین مقصد در 7 روز گذشته
        top_destination = recent_orders.values('destination_port__city__name').annotate(
            order_count=Count('id'),
            total_sales=Sum('final_price')
        ).order_by('-order_count').first()

        # 6. آمار نرخ‌های فعال این فورواردر
        active_rates = Rate.objects.filter(forwarder=forwarder_company, is_active=True)
        total_active_rates = active_rates.count()

        rates_by_route = list(active_rates.values(
            'origin_city__name',
            'destination_city__name',
            'transport_mode'
        ).annotate(rate_count=Count('id')).order_by('-rate_count'))
        for r in rates_by_route:
            r['mode_display'] = mode_choices.get(r['transport_mode'], r['transport_mode'])

        context = {
            'total_orders_count': total_orders_count,
            'total_sales': total_sales,
            'avg_order_amount': int(avg_order_amount),
            'pending_payment_count': pending_payment_count,
            'active_destinations_count': active_destinations_count,
            'top_transport_mode': top_transport_mode,
            'top_destination': top_destination,
            'total_active_rates': total_active_rates,
            'rates_by_route': rates_by_route,
        }

        # کش کوتاه‌مدت (۵ دقیقه): این آمار روزانه‌اند، تازگی لحظه‌ای لازم
        # ندارند؛ فقط برای کاهش بار کوئری‌های تجمیعی روی بازدیدهای پی‌درپی
        # داشبورد است، نه صحت لحظه‌ای.
        if forwarder_company:
            cache.set(f'panel_dashboard:{forwarder_company.id}', context, 300)

    return render(request, 'forwarder_panel/dashboard.html', context)


@login_required
@forwarder_required
@staff_permission_required('can_view_reports')
def get_sales_chart_data(request):
    """
    دریافت داده‌های نمودار فروش بر اساس بازه زمانی و تاریخ (فرمت تاریخ شمسی است).
    """
    forwarder_company = get_company_for_user(request.user)

    # دریافت پارامترها از درخواست GET
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    interval = request.GET.get('interval', 'daily')

    # فیلتر پایه: سفارشات متعلق به این شرکت که پیش‌نویس نیستند
    orders = CargoRequest.objects.filter(
        selected_rate__forwarder=forwarder_company
    ).exclude(status=OrderStatus.DRAFT)

    # تبدیل تاریخ شمسی به میلادی و اعمال فیلتر تاریخ
    try:
        if start_date_str:
            y, m, d = map(int, start_date_str.split('/'))
            start_date = jdatetime.date(y, m, d).togregorian()
            orders = orders.filter(created_at__date__gte=start_date)

        if end_date_str:
            y, m, d = map(int, end_date_str.split('/'))
            end_date = jdatetime.date(y, m, d).togregorian()
            orders = orders.filter(created_at__date__lte=end_date)
    except Exception as e:
        return JsonResponse({'error': 'فرمت تاریخ نامعتبر است. لطفاً فرمت YYYY/MM/DD را رعایت کنید.'}, status=400)

    # انتخاب نوع گروه‌بندی (Truncation) بر اساس بازه زمانی
    trunc_mapping = {
        'daily': TruncDay('created_at'),
        'weekly': TruncWeek('created_at'),
        'monthly': TruncMonth('created_at'),
        'quarterly': TruncQuarter('created_at'),
        'yearly': TruncYear('created_at'),
    }

    trunc_func = trunc_mapping.get(interval, TruncDay('created_at'))

    # گروه‌بندی داده‌ها و محاسبه مجموع مبالغ (فروش)
    sales_data = orders.annotate(
        period=trunc_func
    ).values('period').annotate(
        total_sales=Sum('final_price')
    ).order_by('period')

    # آماده‌سازی آرایه‌ها برای خروجی JSON (فرانت‌اند)
    dates = []
    amounts = []

    for item in sales_data:
        if item['period']:
            # تبدیل مجدد تاریخ میلادی دیتابیس به رشته شمسی برای نمایش در نمودار
            jalali_date = jdatetime.datetime.fromgregorian(datetime=item['period']).strftime('%Y/%m/%d')
            dates.append(jalali_date)
            # اگر مقداری ثبت نشده بود صفر در نظر بگیرد
            amounts.append(item['total_sales'] or 0)

    return JsonResponse({
        'dates': dates,
        'amounts': amounts
    })


@login_required
@forwarder_required
@staff_permission_required('can_view_reports')
def report_view(request):
    """
    نمایش صفحه اصلی گزارشات شامل نمودار فروش
    """
    return render(request, 'forwarder_panel/report.html')
