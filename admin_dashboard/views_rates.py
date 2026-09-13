# admin_dashboard/views_rates.py

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from rates.models import Rate, CargoType, CargoSubCategory

from .decorators import platform_staff_required
from .forms import AdminRateForm
from panel.forms import RateTierFormSet


@login_required
@platform_staff_required
def rate_list(request):
    qs = Rate.objects.select_related(
        "forwarder", "branch", "origin_city", "destination_port__city__country"
    ).order_by("-created_at")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(forwarder__company_name__icontains=q) | Q(origin_city__name__icontains=q)
        )

    active = request.GET.get("active", "").strip()
    if active == "1":
        qs = qs.filter(is_active=True)
    elif active == "0":
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)
    qs_string = params.urlencode()

    context = {
        "page_obj": page_obj,
        "q": q,
        "active": active,
        "querystring": qs_string + "&" if qs_string else "",
    }
    return render(request, "admin_dashboard/rate_list.html", context)


@login_required
@platform_staff_required
def rate_form(request, pk=None):
    instance = get_object_or_404(Rate, pk=pk) if pk else None

    if request.method == "POST":
        form = AdminRateForm(request.POST, instance=instance)
        # همان ترتیب panel/views.py::rate_create_view: فرم‌ست را با
        # form.instance (که هنوز ذخیره نشده) می‌سازیم، هر دو را قبل از ذخیره
        # اعتبارسنجی می‌کنیم و در یک تراکنش ذخیره می‌کنیم.
        tier_formset = RateTierFormSet(request.POST, instance=form.instance)
        if form.is_valid() and tier_formset.is_valid():
            with transaction.atomic():
                rate = form.save()
                tier_formset.instance = rate
                tier_formset.save()
            messages.success(request, "نرخ با موفقیت ذخیره شد.")
            return redirect("staff_dashboard:rate_detail", pk=rate.id)
    else:
        form = AdminRateForm(instance=instance)
        tier_formset = RateTierFormSet(instance=instance)

    context = {"form": form, "tier_formset": tier_formset, "instance": instance}
    return render(request, "admin_dashboard/rate_form.html", context)


@login_required
@platform_staff_required
def rate_detail(request, pk):
    rate = get_object_or_404(
        Rate.objects.select_related(
            "forwarder", "branch",
            "origin_country", "origin_province", "origin_city",
            "destination_country", "destination_city", "destination_port",
        ).prefetch_related("cargo_types", "tiers"),
        pk=pk,
    )
    context = {"rate": rate, "tiers": rate.tiers.all()}
    return render(request, "admin_dashboard/rate_detail.html", context)


@login_required
@platform_staff_required
def rate_delete(request, pk):
    rate = get_object_or_404(Rate, pk=pk)
    if request.method == "POST":
        try:
            rate.delete()
            messages.success(request, "نرخ با موفقیت حذف شد.")
        except ProtectedError:
            messages.error(request, "این نرخ در جای دیگری استفاده شده و قابل حذف نیست.")
            return redirect("staff_dashboard:rate_detail", pk=pk)
        return redirect("staff_dashboard:rate_list")
    return redirect("staff_dashboard:rate_detail", pk=pk)


# ─── دسته‌بندی کالا: دسته اصلی → زیردسته → زیرمجموعه ────────────────────────

@login_required
@platform_staff_required
def cargo_type_hub(request):
    cargo_types = CargoType.objects.all().order_by("name").prefetch_related("subcategories")
    context = {"cargo_types": cargo_types}
    return render(request, "admin_dashboard/cargo_type_hub.html", context)


@login_required
@platform_staff_required
def cargo_subcategory_hub(request, category_id):
    category = get_object_or_404(CargoType, id=category_id)
    subcategories = category.subcategories.all().order_by("name").prefetch_related("children")
    context = {"category": category, "subcategories": subcategories}
    return render(request, "admin_dashboard/cargo_subcategory_hub.html", context)
