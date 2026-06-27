from datetime import timedelta

import jdatetime

from django.db import transaction
from django.db.models import Q, Count, Sum
from django.db.models.functions import (
    TruncDay,
    TruncWeek,
    TruncMonth,
    TruncQuarter,
    TruncYear,
)
from django.utils import timezone

from rest_framework import generics, views, status, permissions
from rest_framework.response import Response

from accounts.models import User
from forwarders.models import ForwarderCompany
from rates.models import Rate, TransportMode
from orders.models import CargoRequest, OrderStatus, OrderHistory

from .permissions import IsForwarderUser
from .serializers import (
    ForwarderOrderListSerializer,
    ForwarderOrderDetailSerializer,
    ForwarderOrderStatusUpdateSerializer,
)


def get_user_forwarder_company(user):
    """
    گرفتن شرکت فورواردر برای هر سه نقش مجاز:

    - FORWARDER_ADMIN:
        از user.forwarder_company

    - FORWARDER_EXPERT / FORWARDER_FINANCE:
        از user.forwarder_staff.company

    این تابع باعث می‌شود منطق API با decorator جدید panel.decorators.forwarder_required
    هماهنگ باشد.
    """

    if not user or not user.is_authenticated:
        return None

    if user.role == User.Role.FORWARDER_ADMIN:
        try:
            return user.forwarder_company
        except ForwarderCompany.DoesNotExist:
            return None

    staff_profile = getattr(user, "forwarder_staff", None)

    if staff_profile:
        return staff_profile.company

    return None


class ForwarderOrderListAPIView(generics.ListAPIView):
    """
    لیست سفارشات فورواردر با قابلیت جستجو و فیلتر.

    مشابه منطق panel.views.order_list_view:

    - فقط سفارش‌های مربوط به شرکت فورواردر کاربر فعلی
    - حذف سفارش‌های draft
    - جستجو بر اساس:
        id
        tracking_code در صورت وجود
        sender_name
        sender_national_id
        sender_phone
        customer.mobile
        customer.first_name
        customer.last_name
    - فیلتر بر اساس:
        country
        city
        mode
        status
    """

    permission_classes = [
        permissions.IsAuthenticated,
        IsForwarderUser,
    ]

    serializer_class = ForwarderOrderListSerializer

    def get_queryset(self):
        forwarder_company = get_user_forwarder_company(self.request.user)

        if not forwarder_company:
            return CargoRequest.objects.none()

        queryset = (
            CargoRequest.objects
            .filter(
                selected_rate__forwarder=forwarder_company
            )
            .exclude(
                status=OrderStatus.DRAFT
            )
            .select_related(
                "customer",
                "destination_port",
                "destination_port__city",
                "destination_port__city__province",
                "destination_port__city__province__country",
                "origin_city",
                "origin_province",
                "origin_country",
                "selected_rate",
                "cargo_type",
            )
            .prefetch_related(
                "cargo_subcategories",
                "dimensions",
            )
            .order_by("-created_at")
        )

        search_query = self.request.query_params.get("q", "").strip()
        country_id = self.request.query_params.get("country")
        city_id = self.request.query_params.get("city")
        mode = self.request.query_params.get("mode")
        order_status = self.request.query_params.get("status")

        if search_query:
            search_filter = (
                Q(id__icontains=search_query) |
                Q(sender_name__icontains=search_query) |
                Q(sender_national_id__icontains=search_query) |
                Q(sender_phone__icontains=search_query) |
                Q(customer__mobile__icontains=search_query) |
                Q(customer__first_name__icontains=search_query) |
                Q(customer__last_name__icontains=search_query)
            )

            # Backward compatibility:
            # اگر فیلد tracking_code واقعاً در مدل وجود داشته باشد، به جستجو اضافه می‌شود.
            cargo_request_fields = [
                field.name
                for field in CargoRequest._meta.get_fields()
            ]

            if "tracking_code" in cargo_request_fields:
                search_filter |= Q(tracking_code__icontains=search_query)

            queryset = queryset.filter(search_filter)

        if country_id:
            queryset = queryset.filter(
                destination_port__city__province__country_id=country_id
            )

        if city_id:
            queryset = queryset.filter(
                destination_port__city_id=city_id
            )

        if mode:
            queryset = queryset.filter(
                transport_mode=mode
            )

        if order_status:
            queryset = queryset.filter(
                status=order_status
            )

        return queryset


class ForwarderOrderDetailAPIView(generics.RetrieveAPIView):
    """
    جزئیات سفارش فورواردر.

    این view در urls فعلی شما ثبت نشده، اما برای کامل بودن API و استفاده آینده آماده است.
    اگر خواستی می‌توانی این مسیر را به urls اضافه کنی:

    path('orders/<int:pk>/', views.ForwarderOrderDetailAPIView.as_view(), name='forwarder-order-detail')
    """

    permission_classes = [
        permissions.IsAuthenticated,
        IsForwarderUser,
    ]

    serializer_class = ForwarderOrderDetailSerializer

    def get_queryset(self):
        forwarder_company = get_user_forwarder_company(self.request.user)

        if not forwarder_company:
            return CargoRequest.objects.none()

        return (
            CargoRequest.objects
            .filter(
                selected_rate__forwarder=forwarder_company
            )
            .exclude(
                status=OrderStatus.DRAFT
            )
            .select_related(
                "customer",
                "selected_rate",
                "selected_rate__forwarder",
                "origin_country",
                "origin_province",
                "origin_city",
                "destination_port",
                "destination_port__city",
                "cargo_type",
            )
            .prefetch_related(
                "cargo_subcategories",
                "dimensions",
            )
        )


class ForwarderOrderStatusUpdateAPIView(views.APIView):
    """
    تغییر وضعیت یک سفارش توسط فورواردر همراه با ثبت OrderHistory.

    منطق مشابه panel.views.order_detail_view و order_list_view:

    - فقط سفارش‌هایی که selected_rate.forwarder آن‌ها متعلق به شرکت کاربر است
    - ثبت لاگ تغییر وضعیت در OrderHistory
    - استفاده از transaction.atomic برای امنیت تراکنش
    """

    permission_classes = [
        permissions.IsAuthenticated,
        IsForwarderUser,
    ]

    def post(self, request, pk=None, order_id=None):
        """
        pk برای سازگاری با urls فعلی:

        path('orders/<int:pk>/status/', ...)

        order_id هم گذاشته شده تا اگر جای دیگری با این نام صدا زده شد، نشکند.
        """

        forwarder_company = get_user_forwarder_company(request.user)

        if not forwarder_company:
            return Response(
                {
                    "detail": "شرکت فورواردر برای کاربر فعلی یافت نشد."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        order_pk = pk or order_id

        try:
            order = CargoRequest.objects.get(
                id=order_pk,
                selected_rate__forwarder=forwarder_company,
            )

        except CargoRequest.DoesNotExist:
            return Response(
                {
                    "detail": "سفارش یافت نشد یا شما به آن دسترسی ندارید."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ForwarderOrderStatusUpdateSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        note = serializer.validated_data.get("note") or ""

        old_status = order.status

        if old_status == new_status:
            return Response(
                {
                    "detail": "وضعیت انتخاب‌شده با وضعیت فعلی سفارش یکسان است.",
                    "old_status": old_status,
                    "new_status": new_status,
                    "changed": False,
                },
                status=status.HTTP_200_OK
            )

        with transaction.atomic():
            order.status = new_status
            order.save(update_fields=["status"])

            OrderHistory.objects.create(
                order=order,
                changed_by=request.user,
                field_name="status",
                old_value=old_status,
                new_value=new_status,
                note=note,
            )

        return Response(
            {
                "detail": "وضعیت سفارش با موفقیت تغییر کرد.",
                "old_status": old_status,
                "new_status": new_status,
                "changed": True,
            },
            status=status.HTTP_200_OK
        )


class ForwarderDashboardAPIView(views.APIView):
    """
    داشبورد فورواردر.

    هماهنگ با panel.views.dashboard_view و تا حدی get_sales_chart_data:

    خروجی شامل:
    - total_orders_count
    - total_sales
    - top_transport_mode
    - top_destination
    - total_active_rates
    - rates_by_route
    - sales_chart

    Query Params اختیاری برای نمودار:
    - start_date با فرمت شمسی YYYY/MM/DD
    - end_date با فرمت شمسی YYYY/MM/DD
    - interval:
        daily
        weekly
        monthly
        quarterly
        yearly
    """

    permission_classes = [
        permissions.IsAuthenticated,
        IsForwarderUser,
    ]

    def get(self, request, *args, **kwargs):
        forwarder_company = get_user_forwarder_company(request.user)

        if not forwarder_company:
            return Response(
                {
                    "detail": "شرکت فورواردر برای کاربر فعلی یافت نشد."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        seven_days_ago = timezone.now() - timedelta(days=7)

        all_orders = (
            CargoRequest.objects
            .filter(
                selected_rate__forwarder=forwarder_company
            )
            .exclude(
                status=OrderStatus.DRAFT
            )
        )

        recent_orders = all_orders.filter(
            created_at__gte=seven_days_ago
        )

        total_orders_count = recent_orders.count()

        total_sales = recent_orders.aggregate(
            total=Sum("final_price")
        )["total"] or 0

        top_transport_mode = (
            recent_orders
            .values("transport_mode")
            .annotate(
                order_count=Count("id"),
                total_sales=Sum("final_price"),
            )
            .order_by("-order_count")
            .first()
        )

        mode_choices = dict(TransportMode.choices)

        if top_transport_mode:
            top_transport_mode["display_name"] = mode_choices.get(
                top_transport_mode["transport_mode"],
                top_transport_mode["transport_mode"],
            )

        top_destination = (
            recent_orders
            .values("destination_port__city__name")
            .annotate(
                order_count=Count("id"),
                total_sales=Sum("final_price"),
            )
            .order_by("-order_count")
            .first()
        )

        active_rates = Rate.objects.filter(
            forwarder=forwarder_company,
            is_active=True,
        )

        total_active_rates = active_rates.count()

        rates_by_route_queryset = (
            active_rates
            .values(
                "origin_city__name",
                "destination_city__name",
                "transport_mode",
            )
            .annotate(
                rate_count=Count("id")
            )
            .order_by("-rate_count")
        )

        rates_by_route = []

        for item in rates_by_route_queryset:
            transport_mode = item.get("transport_mode")

            rates_by_route.append({
                "origin_city_name": item.get("origin_city__name"),
                "destination_city_name": item.get("destination_city__name"),
                "transport_mode": transport_mode,
                "mode_display": mode_choices.get(
                    transport_mode,
                    transport_mode
                ),
                "rate_count": item.get("rate_count", 0),
            })

        sales_chart = self.get_sales_chart_data(
            request=request,
            base_queryset=all_orders,
        )

        return Response(
            {
                "total_orders_count": total_orders_count,
                "total_sales": total_sales,

                "top_transport_mode": top_transport_mode,
                "top_destination": top_destination,

                "total_active_rates": total_active_rates,
                "rates_by_route": rates_by_route,

                "sales_chart": sales_chart,
            },
            status=status.HTTP_200_OK
        )

    def get_sales_chart_data(self, request, base_queryset):
        """
        تولید داده نمودار فروش.

        اگر start_date و end_date ارسال نشوند، تمام سفارش‌های غیر Draft
        مربوط به همین فورواردر مبنای نمودار قرار می‌گیرند.
        """

        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")
        interval = request.query_params.get("interval", "daily")

        orders = base_queryset

        try:
            if start_date_str:
                y, m, d = map(int, start_date_str.split("/"))
                start_date = jdatetime.date(y, m, d).togregorian()

                orders = orders.filter(
                    created_at__date__gte=start_date
                )

            if end_date_str:
                y, m, d = map(int, end_date_str.split("/"))
                end_date = jdatetime.date(y, m, d).togregorian()

                orders = orders.filter(
                    created_at__date__lte=end_date
                )

        except Exception:
            return {
                "error": "فرمت تاریخ نامعتبر است. فرمت صحیح: YYYY/MM/DD",
                "dates": [],
                "amounts": [],
            }

        trunc_mapping = {
            "daily": TruncDay("created_at"),
            "weekly": TruncWeek("created_at"),
            "monthly": TruncMonth("created_at"),
            "quarterly": TruncQuarter("created_at"),
            "yearly": TruncYear("created_at"),
        }

        trunc_func = trunc_mapping.get(
            interval,
            TruncDay("created_at")
        )

        sales_data = (
            orders
            .annotate(
                period=trunc_func
            )
            .values("period")
            .annotate(
                total_sales=Sum("final_price"),
                order_count=Count("id"),
            )
            .order_by("period")
        )

        dates = []
        amounts = []
        order_counts = []

        for item in sales_data:
            period = item.get("period")

            if not period:
                continue

            jalali_date = jdatetime.datetime.fromgregorian(
                datetime=period
            ).strftime("%Y/%m/%d")

            dates.append(jalali_date)
            amounts.append(item.get("total_sales") or 0)
            order_counts.append(item.get("order_count") or 0)

        return {
            "interval": interval,
            "dates": dates,
            "amounts": amounts,
            "order_counts": order_counts,
        }
