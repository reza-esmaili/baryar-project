# admin_dashboard/views_land.py — پایش درخواست‌های حمل زمینی (اعلام بار)

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from land_freight.models import LandFreightRequest, LandRequestStatus, LandServiceScope
from land_freight.services import expire_stale_requests

from .decorators import platform_staff_required
from .views import _querystring


@login_required
@platform_staff_required
def land_request_list(request):
    expire_stale_requests()

    qs = (
        LandFreightRequest.objects.select_related(
            "customer", "origin_city", "destination_city", "foreign_country", "foreign_city",
            "vehicle_type", "assigned_company",
        )
        .annotate(dispatch_count=Count("dispatches"))
        .order_by("-created_at")
    )

    q = request.GET.get("q", "").strip()
    if q:
        filters = Q(customer__mobile__icontains=q) | Q(assigned_company__company_name__icontains=q)
        digits = q.upper().replace("LF-", "")
        if digits.isdigit():
            filters |= Q(pk=int(digits))
        qs = qs.filter(filters)

    status = request.GET.get("status")
    if status in LandRequestStatus.values:
        qs = qs.filter(status=status)
    scope = request.GET.get("scope")
    if scope in LandServiceScope.values:
        qs = qs.filter(scope=scope)

    page_obj = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "admin_dashboard/land_request_list.html", {
        "page_obj": page_obj,
        "querystring": _querystring(request),
        "q": q,
        "statuses": LandRequestStatus.choices,
        "scopes": LandServiceScope.choices,
        "selected_status": status,
        "selected_scope": scope,
    })


@login_required
@platform_staff_required
def land_request_detail(request, pk):
    land_request = get_object_or_404(
        LandFreightRequest.objects.select_related(
            "customer", "origin_city", "destination_city", "foreign_country", "foreign_city",
            "border_crossing", "cargo_type", "vehicle_type", "loader_type", "assigned_company", "assigned_by",
        ),
        pk=pk,
    )
    return render(request, "admin_dashboard/land_request_detail.html", {
        "req": land_request,
        "dispatches": land_request.dispatches.select_related("company").order_by("sent_at"),
        "events": land_request.events.select_related("actor").all(),
    })
