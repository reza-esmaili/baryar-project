from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from accounts.models import User
from locations.models import City, DestinationCity, Port

from .forms import LandFreightRequestForm
from .models import (
    ACTIVE_ASSIGNED_STATUSES,
    DispatchStatus,
    LandFreightRequest,
    LandRequestStatus,
    LandServiceScope,
)
from .services import (
    LandRequestError,
    cancel_request,
    expire_stale_requests,
    publish_request,
    republish_request,
)


def customer_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.role != User.Role.CUSTOMER:
            messages.error(request, "ثبت و پیگیری درخواست حمل زمینی فقط برای حساب‌های مشتری امکان‌پذیر است.")
            return redirect("core:home")
        return view_func(request, *args, **kwargs)
    return _wrapped


def _customer_request_or_404(request, pk):
    return get_object_or_404(
        LandFreightRequest.objects.select_related(
            "origin_city__province", "destination_city__province", "foreign_country", "foreign_city",
            "border_crossing", "cargo_type", "vehicle_type", "loader_type", "assigned_company",
        ),
        pk=pk,
        customer=request.user,
    )


@login_required
@customer_required
def request_create(request):
    initial_scope = request.GET.get("scope")
    if request.method == "POST":
        form = LandFreightRequestForm(request.POST, user=request.user)
        if form.is_valid():
            land_request = form.save(commit=False)
            land_request.customer = request.user
            land_request.status = LandRequestStatus.OPEN
            land_request.expires_at = LandFreightRequest.default_expiry(land_request.scope)
            land_request.save()
            carriers = publish_request(land_request, request.user)

            if carriers:
                messages.success(
                    request,
                    f"درخواست {land_request.reference} ثبت و برای {carriers} شرکت حمل واجد شرایط ارسال شد. "
                    f"به محض پذیرش توسط اولین شرکت، اطلاعات آن را همین‌جا می‌بینید.",
                )
            else:
                messages.warning(
                    request,
                    f"درخواست {land_request.reference} ثبت شد، اما در حال حاضر شرکت حمل واجد شرایطی برای این "
                    f"مسیر و ناوگان وجود ندارد. می‌توانید نوع ناوگان یا کرایه را تغییر دهید و دوباره منتشر کنید.",
                )
            return redirect("land_freight:request_detail", pk=land_request.pk)
        messages.error(request, "لطفاً خطاهای فرم را بررسی و اصلاح کنید.")
    else:
        scope = initial_scope if initial_scope in LandServiceScope.values else LandServiceScope.DOMESTIC
        form = LandFreightRequestForm(user=request.user, initial={"scope": scope})

    return render(request, "land_freight/request_form.html", {
        "form": form,
        "scopes": LandServiceScope,
    })


@login_required
@customer_required
def request_list(request):
    expire_stale_requests()

    requests_qs = (
        LandFreightRequest.objects.filter(customer=request.user)
        .select_related("origin_city", "destination_city", "foreign_country", "foreign_city",
                        "vehicle_type", "assigned_company")
        .annotate(dispatch_count=Count("dispatches"))
    )
    status = request.GET.get("status")
    if status in LandRequestStatus.values:
        requests_qs = requests_qs.filter(status=status)

    page_obj = Paginator(requests_qs, 15).get_page(request.GET.get("page"))
    return render(request, "land_freight/request_list.html", {
        "page_obj": page_obj,
        "requests": page_obj,
        "statuses": LandRequestStatus.choices,
        "current_status": status,
    })


def _dispatch_stats(land_request):
    return land_request.dispatches.aggregate(
        total=Count("id"),
        seen=Count("id", filter=Q(status__in=[DispatchStatus.SEEN, DispatchStatus.ACCEPTED, DispatchStatus.MISSED])),
    )


@login_required
@customer_required
def request_detail(request, pk):
    expire_stale_requests()
    land_request = _customer_request_or_404(request, pk)

    return render(request, "land_freight/request_detail.html", {
        "req": land_request,
        "stats": _dispatch_stats(land_request),
        "events": land_request.events.select_related("actor").all(),
        "carrier_visible": land_request.status in (*ACTIVE_ASSIGNED_STATUSES, LandRequestStatus.DELIVERED),
        "Status": LandRequestStatus,
    })


@login_required
@customer_required
@require_GET
def request_status(request, pk):
    """برای به‌روزرسانی زنده‌ی صفحه‌ی جزئیات تا زمان پذیرش."""
    expire_stale_requests()
    land_request = _customer_request_or_404(request, pk)
    stats = _dispatch_stats(land_request)
    return JsonResponse({
        "status": land_request.status,
        "status_label": land_request.get_status_display(),
        "dispatched": stats["total"],
        "seen": stats["seen"],
    })


@login_required
@customer_required
@require_POST
def request_cancel(request, pk):
    land_request = _customer_request_or_404(request, pk)
    try:
        cancel_request(land_request, request.user, request.POST.get("reason", "").strip())
        messages.success(request, f"درخواست {land_request.reference} لغو شد.")
    except LandRequestError as exc:
        messages.error(request, str(exc))
    return redirect("land_freight:request_detail", pk=land_request.pk)


@login_required
@customer_required
@require_POST
def request_republish(request, pk):
    land_request = _customer_request_or_404(request, pk)
    raw_price = (request.POST.get("proposed_price") or "").replace(",", "").strip()
    try:
        new_price = Decimal(raw_price)
    except InvalidOperation:
        messages.error(request, "کرایه‌ی وارد‌شده معتبر نیست.")
        return redirect("land_freight:request_detail", pk=land_request.pk)

    try:
        carriers = republish_request(land_request, request.user, new_price)
        messages.success(request, f"درخواست با کرایه‌ی جدید دوباره برای {carriers} شرکت ارسال شد.")
    except LandRequestError as exc:
        messages.error(request, str(exc))
    return redirect("land_freight:request_detail", pk=land_request.pk)


# ─── AJAX: فهرست‌های وابسته‌ی فرم ────────────────────────────────────────────

@login_required
@require_GET
def ajax_cities(request):
    province_id = request.GET.get("province_id")
    cities = City.objects.none()
    if province_id:
        cities = City.objects.filter(
            province_id=province_id, is_active=True, province__country__code="IRN",
        ).order_by("name")
    return JsonResponse(list(cities.values("id", "name")), safe=False)


@login_required
@require_GET
def ajax_foreign_cities(request):
    country_id = request.GET.get("country_id")
    cities = DestinationCity.objects.none()
    if country_id:
        cities = DestinationCity.objects.filter(country_id=country_id, is_active=True).order_by("name")
    return JsonResponse(list(cities.values("id", "name")), safe=False)


@login_required
@require_GET
def ajax_border_crossings(request):
    country_id = request.GET.get("country_id")
    ports = Port.objects.none()
    if country_id:
        ports = Port.objects.filter(
            city__country_id=country_id, port_type="land", is_active=True,
        ).order_by("name")
    return JsonResponse(list(ports.values("id", "name")), safe=False)
