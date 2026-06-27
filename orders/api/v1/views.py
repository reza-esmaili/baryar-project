from rest_framework import generics, permissions, status
from rest_framework.response import Response

from django.db.models import Prefetch

from orders.models import CargoRequest, OrderHistory
from orders.services import calculate_and_match_rates

from .serializers import (
    CargoRequestSerializer,
    RateCalculationRequestSerializer,
    OrderHistorySerializer,
)
from orders.crosssite import create_order_token
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
import hmac, hashlib


class CalculateRatesAPIView(generics.GenericAPIView):
    """
    API محاسبه نرخ بدون ذخیره سفارش در دیتابیس.

    مشابه ajax_calculate_rates در views.py اصلی.
    """

    serializer_class = RateCalculationRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data

        dimensions = validated_data.get('dimensions', [])
        transport_mode = validated_data.get('transport_mode')

        is_fcl = transport_mode in ['sea_fcl', 'FCL']

        calculation_payload = {
            'origin_country': validated_data.get('origin_country'),
            'origin_province': validated_data.get('origin_province'),
            'origin_city': validated_data.get('origin_city'),
            'destination_port': validated_data.get('destination_port'),
            'transport_mode': validated_data.get('transport_mode'),
            'shipping_procedure': validated_data.get('shipping_procedure'),
            'cargo_type': validated_data.get('cargo_type'),
            'actual_weight': validated_data.get('actual_weight'),

            'container_size': validated_data.get('container_size'),
            'container_type': validated_data.get('container_type'),
            'container_count': validated_data.get('container_count'),

            'needs_office_packaging': validated_data.get(
                'needs_office_packaging',
                False
            ),
            'needs_onsite_packaging': validated_data.get(
                'needs_onsite_packaging',
                False
            ),
            'needs_doorstep_packaging': validated_data.get(
                'needs_doorstep_packaging',
                False
            ),

            'cargo_subcategories': validated_data.get(
                'cargo_subcategories',
                []
            ),
            'other_cargo_details': validated_data.get(
                'other_cargo_details'
            ),
        }

        service_dimensions = [] if is_fcl else dimensions

        result = calculate_and_match_rates(
            calculation_payload,
            service_dimensions
        )

        return Response(
            {
                'success': True,
                'message': 'نرخ‌ها با موفقیت محاسبه شدند.',
                'actual_weight': result.get('actual_weight', 0),
                'volumetric_weight': result.get('volumetric_weight', 0),
                'chargeable_weight': result.get('chargeable_weight', 0),
                'rates': result.get('results', []),
            },
            status=status.HTTP_200_OK
        )


class CargoRequestListCreateAPIView(generics.ListCreateAPIView):
    """
    لیست سفارش‌های کاربر و ایجاد سفارش جدید.

    ایجاد سفارش از طریق این API:
    - سفارش را برای user لاگین‌شده ثبت می‌کند.
    - اگر selected_rate ارسال شده باشد، قیمت را دوباره از سمت سرور محاسبه می‌کند.
    - وضعیت اولیه را DRAFT می‌گذارد.
    """

    serializer_class = CargoRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            CargoRequest.objects
            .filter(customer=self.request.user)
            .select_related(
                'customer',
                'origin_country',
                'origin_province',
                'origin_city',
                'destination_port',
                'cargo_type',
                'selected_rate',
                'sender_province',
                'sender_city',
            )
            .prefetch_related(
                'cargo_subcategories',
                'dimensions',
            )
            .order_by('-created_at')
        )

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)


class CargoRequestDetailAPIView(generics.RetrieveUpdateAPIView):
    """
    دریافت و ویرایش سفارش کاربر.

    نکته:
    - فقط سفارش‌های متعلق به کاربر لاگین‌شده قابل مشاهده/ویرایش هستند.
    - قیمت‌ها از سمت کلاینت پذیرفته نمی‌شوند.
    - در صورت تغییر selected_rate یا اطلاعات اصلی، محاسبه قیمت دوباره انجام می‌شود.
    """

    serializer_class = CargoRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            CargoRequest.objects
            .filter(customer=self.request.user)
            .select_related(
                'customer',
                'origin_country',
                'origin_province',
                'origin_city',
                'destination_port',
                'cargo_type',
                'selected_rate',
                'sender_province',
                'sender_city',
            )
            .prefetch_related(
                'cargo_subcategories',
                'dimensions',
            )
        )


class CargoRequestHistoryAPIView(generics.ListAPIView):
    """
    لیست تاریخچه یک سفارش.

    اگر خواستی در urls.py هم اضافه کنی:
    path('requests/<int:pk>/history/', CargoRequestHistoryAPIView.as_view(), name='cargo_request_history')
    """

    serializer_class = OrderHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        order_id = self.kwargs.get('pk')

        return (
            OrderHistory.objects
            .filter(
                order_id=order_id,
                order__customer=self.request.user
            )
            .select_related(
                'order',
                'changed_by',
            )
            .order_by('-created_at')
        )
# ════════════════════════════════════════════════════════════════
# فایل: baryar/orders/api/v1/views.py
# اضافه کن به انتهای فایل موجود
# ════════════════════════════════════════════════════════════════

# ── Import های جدید که باید به ابتدای فایل اضافه کنی ─────────────
# from orders.crosssite import create_order_token
# from rest_framework.permissions import IsAuthenticated
# from django.conf import settings
# import hmac, hashlib


class CreateCrossSiteOrderTokenView(generics.GenericAPIView):
    """
    API برای ساخت توکن یکبار مصرف cross-site.

    Tejarat با JWT سرویس این endpoint را صدا می‌زند،
    داده‌های سفارش را می‌فرستد،
    و یک token کوتاه‌مدت (۵ دقیقه) دریافت می‌کند.

    POST /api/v1/orders/crosssite-token/
    Authorization: Bearer <service_jwt>

    Body:
    {
        "rate_id": 5,
        "origin_city": 12,
        "destination_port": 3,
        "transport_mode": "air",
        "cargo_type": 2,
        "shipping_procedure": "commercial",
        "actual_weight": 100.0,
        "dimensions": [{"length":50,"width":40,"height":30,"quantity":2}],
        "needs_office_packaging": false,
        "needs_onsite_packaging": false,
        "needs_doorstep_packaging": false
    }

    Response:
    {
        "token": "abc123...",
        "redirect_url": "https://baryar.com/orders/crosssite-login/?token=abc123..."
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        from orders.crosssite import create_order_token
        from rates.models import Rate
        from locations.models import City, Port
        from rates.models import CargoType

        data = request.data

        # ── اعتبارسنجی فیلدهای اجباری ────────────────────────
        required = ['rate_id', 'origin_city', 'destination_port',
                    'transport_mode', 'cargo_type', 'shipping_procedure']

        missing = [f for f in required if not data.get(f)]
        if missing:
            return Response(
                {"success": False, "error": f"فیلدهای ناقص: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── بررسی وجود rate_id ────────────────────────────────
        try:
            rate = Rate.objects.get(id=data['rate_id'], is_active=True)
        except Rate.DoesNotExist:
            return Response(
                {"success": False, "error": "نرخ انتخاب‌شده معتبر نیست یا منقضی شده است."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── بررسی اینکه rate هنوز valid_until داره ────────────
        from django.utils import timezone as tz
        if rate.valid_until and rate.valid_until < tz.now().date():
            return Response(
                {"success": False, "error": "نرخ انتخاب‌شده منقضی شده است."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── ساختن payload سفارش (بدون قیمت — قیمت server-side محاسبه می‌شود) ──
        order_data = {
            "rate_id":            int(data['rate_id']),
            "origin_city":        int(data['origin_city']),
            "destination_port":   int(data['destination_port']),
            "transport_mode":     str(data['transport_mode']),
            "cargo_type":         int(data['cargo_type']),
            "shipping_procedure": str(data['shipping_procedure']),
            "actual_weight":      float(data.get('actual_weight') or 0),
            "dimensions":         data.get('dimensions', []),
            "container_size":     data.get('container_size'),
            "container_type":     data.get('container_type'),
            "container_count":    int(data.get('container_count') or 1),
            "needs_office_packaging":   bool(data.get('needs_office_packaging', False)),
            "needs_onsite_packaging":   bool(data.get('needs_onsite_packaging', False)),
            "needs_doorstep_packaging": bool(data.get('needs_doorstep_packaging', False)),
        }

        token = create_order_token(order_data)

        # URL که کاربر به آن هدایت می‌شود
        base_url = getattr(settings, 'BARYAR_BASE_URL', request.build_absolute_uri('/').rstrip('/'))
        redirect_url = f"{base_url}/orders/crosssite-login/?token={token}"

        return Response({
            "success":      True,
            "token":        token,
            "redirect_url": redirect_url,
            "expires_in":   300,  # ثانیه
        }, status=status.HTTP_200_OK)