# ==============================================================================
# حمل زمینی (اعلام بار) — صندوق درخواست‌ها و پیگیری در پنل فورواردر
# ==============================================================================

from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from land_freight.forms import LandCarrierProfileForm
from land_freight.models import (
    ACTIVE_ASSIGNED_STATUSES,
    OPEN_DISPATCH_STATUSES,
    DispatchStatus,
    LandCarrierProfile,
    LandDocumentStatus,
    LandFreightRequest,
    LandRequestDispatch,
    LandRequestDocument,
    LandRequestStatus,
)
from land_freight.services import (
    LandRequestError,
    accept_request,
    decline_request,
    expire_stale_requests,
    land_documents_summary,
    mark_seen,
    review_land_document,
    update_carrier_status,
)

from .decorators import forwarder_required, get_company_for_user, staff_perm, staff_permission_required


def land_carrier_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        company = get_company_for_user(request.user)
        if not company or not company.offers_land:
            messages.warning(request, "شرکت شما در دسته‌های حمل زمینی فعال نیست.")
            return redirect("forwarder_panel:dashboard")
        request.forwarder_company = company
        return view_func(request, *args, **kwargs)
    return _wrapped


TABS = {
    "open": "درخواست‌های باز",
    "mine": "پذیرفته‌شده توسط ما",
    "history": "ردشده / از دست رفته / بسته‌شده",
}


@login_required
@forwarder_required
@staff_permission_required("can_view_land_requests")
@land_carrier_required
def land_request_list(request):
    expire_stale_requests()
    company = request.forwarder_company
    tab = request.GET.get("tab", "open")
    if tab not in TABS:
        tab = "open"

    base = LandFreightRequest.objects.select_related(
        "origin_city", "destination_city", "foreign_country", "foreign_city", "vehicle_type", "cargo_type",
    )
    now = timezone.now()

    # شرط شرکت و وضعیت ارسال در یک filter تا هر دو روی همان ردیف ارسال اعمال شوند.
    open_filter = {
        "dispatches__company": company,
        "dispatches__status__in": OPEN_DISPATCH_STATUSES,
        "status": LandRequestStatus.OPEN,
        "expires_at__gt": now,
    }
    if tab == "open":
        qs = base.filter(**open_filter).order_by("expires_at")
    elif tab == "mine":
        qs = base.filter(assigned_company=company).order_by("-assigned_at")
    else:
        qs = base.filter(
            dispatches__company=company,
            dispatches__status__in=[DispatchStatus.MISSED, DispatchStatus.CLOSED, DispatchStatus.DECLINED],
        ).order_by("-updated_at")

    counts = {
        "open": LandFreightRequest.objects.filter(**open_filter).distinct().count(),
        "mine": LandFreightRequest.objects.filter(
            assigned_company=company, status__in=ACTIVE_ASSIGNED_STATUSES,
        ).count(),
    }

    page_obj = Paginator(qs.distinct(), 20).get_page(request.GET.get("page"))
    # وضعیت ارسالِ هر ردیف برای همین شرکت (دیده‌نشده / ردشده / از دست رفته)
    dispatch_status = dict(
        LandRequestDispatch.objects.filter(
            company=company, request_id__in=[r.pk for r in page_obj],
        ).values_list("request_id", "status")
    )
    for land_request in page_obj:
        land_request.company_dispatch_status = dispatch_status.get(land_request.pk)

    return render(request, "forwarder_panel/land_request_list.html", {
        "page_obj": page_obj,
        "requests": page_obj,
        "tab": tab,
        "tabs": TABS,
        "counts": counts,
        "querystring": f"tab={tab}&",
    })


@login_required
@forwarder_required
@staff_permission_required("can_view_land_requests")
@land_carrier_required
def land_request_detail(request, pk):
    expire_stale_requests()
    company = request.forwarder_company
    land_request = get_object_or_404(
        LandFreightRequest.objects.select_related(
            "customer", "origin_city__province", "destination_city__province", "foreign_country",
            "foreign_city", "border_crossing", "cargo_type", "vehicle_type", "loader_type", "assigned_company",
        ),
        pk=pk,
    )

    dispatch = LandRequestDispatch.objects.filter(request=land_request, company=company).first()
    is_ours = land_request.assigned_company_id == company.id
    if not dispatch and not is_ours:
        messages.error(request, "این درخواست برای شرکت شما ارسال نشده است.")
        return redirect("forwarder_panel:land_request_list")

    if dispatch:
        mark_seen(land_request, company)
        dispatch.refresh_from_db()

    can_act = staff_perm(request.user, "can_accept_land_requests")
    dispatch_open = bool(dispatch and dispatch.status in OPEN_DISPATCH_STATUSES)
    return render(request, "forwarder_panel/land_request_detail.html", {
        "req": land_request,
        "dispatch": dispatch,
        "is_ours": is_ours,
        # اطلاعات تماس و آدرس دقیق مشتری فقط پس از پذیرش برای شرکت برنده نمایش داده می‌شود.
        "show_contact": is_ours,
        "can_accept": land_request.is_open_for_acceptance and dispatch_open and can_act,
        "can_decline": land_request.is_open_for_acceptance and dispatch_open and can_act,
        "can_update": is_ours and can_act,
        "can_review_documents": is_ours and can_act,
        "Status": LandRequestStatus,
        "DispatchStatus": DispatchStatus,
        "DocStatus": LandDocumentStatus,
        # فهرست مدارک لازم پیش از پذیرش هم دیده می‌شود (برای تصمیم‌گیری)، اما فایل‌ها فقط برای برنده.
        "documents": land_request.documents.select_related("document_type").all(),
        "documents_summary": land_documents_summary(land_request),
        "events": land_request.events.select_related("actor").all() if is_ours else None,
    })


@login_required
@forwarder_required
@staff_permission_required("can_accept_land_requests")
@land_carrier_required
@require_POST
def land_request_decline(request, pk):
    company = request.forwarder_company
    land_request = get_object_or_404(LandFreightRequest, pk=pk)
    try:
        decline_request(land_request, company, request.POST.get("reason", ""))
        messages.success(request, f"درخواست {land_request.reference} رد شد و از صندوق باز شما حذف شد.")
        return redirect("forwarder_panel:land_request_list")
    except LandRequestError as exc:
        messages.error(request, str(exc))
    return redirect("forwarder_panel:land_request_detail", pk=pk)


@login_required
@forwarder_required
@staff_permission_required("can_accept_land_requests")
@land_carrier_required
@require_POST
def land_document_review(request, pk, document_id):
    company = request.forwarder_company
    document = get_object_or_404(
        LandRequestDocument.objects.select_related("request__customer", "document_type"),
        pk=document_id, request_id=pk,
    )
    approve = request.POST.get("action") == "approve"
    try:
        review_land_document(document, company, request.user, approve, request.POST.get("reason", ""))
        messages.success(
            request, f"مدرک «{document.document_type.title}» {'تایید' if approve else 'رد'} شد و به مشتری اطلاع داده شد.",
        )
    except LandRequestError as exc:
        messages.error(request, str(exc))
    return redirect(f"{reverse('forwarder_panel:land_request_detail', args=[pk])}#documents")


@login_required
@forwarder_required
@staff_permission_required("can_accept_land_requests")
@land_carrier_required
@require_POST
def land_request_accept(request, pk):
    company = request.forwarder_company
    try:
        expected_price = Decimal(request.POST.get("expected_price", ""))
    except InvalidOperation:
        messages.error(request, "درخواست نامعتبر است؛ صفحه را دوباره بارگذاری کنید.")
        return redirect("forwarder_panel:land_request_detail", pk=pk)

    try:
        land_request = accept_request(pk, company, request.user, expected_price)
        messages.success(
            request,
            f"درخواست {land_request.reference} به نام شرکت شما ثبت شد. اطلاعات تماس مشتری اکنون در دسترس است.",
        )
    except LandRequestError as exc:
        messages.error(request, str(exc))
    return redirect("forwarder_panel:land_request_detail", pk=pk)


@login_required
@forwarder_required
@staff_permission_required("can_accept_land_requests")
@land_carrier_required
@require_POST
def land_request_update_status(request, pk):
    company = request.forwarder_company
    land_request = get_object_or_404(LandFreightRequest, pk=pk, assigned_company=company)
    try:
        update_carrier_status(land_request, company, request.user, request.POST.get("status"))
        messages.success(request, f"وضعیت درخواست به «{land_request.get_status_display()}» تغییر کرد.")
    except LandRequestError as exc:
        messages.error(request, str(exc))
    return redirect("forwarder_panel:land_request_detail", pk=pk)


@login_required
@forwarder_required
@land_carrier_required
def land_service_area(request):
    company = request.forwarder_company
    profile, _ = LandCarrierProfile.objects.get_or_create(company=company)
    can_edit = request.user.role == User.Role.FORWARDER_ADMIN

    if request.method == "POST":
        if not can_edit:
            messages.error(request, "فقط ادمین شرکت می‌تواند حوزه‌ی فعالیت را تغییر دهد.")
            return redirect("forwarder_panel:land_service_area")
        form = LandCarrierProfileForm(request.POST, instance=profile, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, "حوزه‌ی فعالیت حمل زمینی ذخیره شد.")
            return redirect("forwarder_panel:land_service_area")
        messages.error(request, "لطفاً خطاهای فرم را بررسی کنید.")
    else:
        form = LandCarrierProfileForm(instance=profile, company=company)

    return render(request, "forwarder_panel/land_service_area.html", {
        "form": form,
        "company": company,
        "can_edit": can_edit,
    })
