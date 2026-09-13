# admin_dashboard/views_lookup.py
#
# موتور عمومی برای جدول‌های مرجع ساده (رجیستری در lookups.py). به‌جای نوشتن
# یک ویو مجزا برای هر مدل، یک لیست/فرم عمومی که بر اساس LookupConfig کار
# می‌کند استفاده می‌شود.

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import platform_staff_required
from .lookups import LOOKUPS


def _get_config(key):
    config = LOOKUPS.get(key)
    if not config:
        raise Http404("جدول مرجع نامعتبر است.")
    return config


def _resolve_attr(obj, path):
    value = obj
    for part in path.split("."):
        value = getattr(value, part, None)
        if callable(value):
            value = value()
        if value is None:
            return "-"
    return value


@login_required
@platform_staff_required
def lookup_list(request, key):
    config = _get_config(key)
    qs = config.base_queryset()

    q = request.GET.get("q", "").strip()
    if q and config.search_fields:
        filters = Q()
        for field in config.search_fields:
            filters |= Q(**{f"{field}__icontains": q})
        qs = qs.filter(filters)

    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = []
    for obj in page_obj:
        rows.append({
            "obj": obj,
            "values": [_resolve_attr(obj, path) for path, _ in config.columns],
        })

    params = request.GET.copy()
    params.pop("page", None)
    qs_string = params.urlencode()

    context = {
        "config": config,
        "page_obj": page_obj,
        "rows": rows,
        "q": q,
        "querystring": qs_string + "&" if qs_string else "",
    }
    return render(request, "admin_dashboard/lookup_list.html", context)


@login_required
@platform_staff_required
def lookup_form(request, key, pk=None):
    config = _get_config(key)
    instance = get_object_or_404(config.model, pk=pk) if pk else None

    if request.method == "POST":
        form = config.form_class(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "با موفقیت ذخیره شد.")
            return redirect("staff_dashboard:lookup_list", key=key)
    else:
        form = config.form_class(instance=instance)

    context = {"config": config, "form": form, "instance": instance}
    return render(request, "admin_dashboard/lookup_form.html", context)


@login_required
@platform_staff_required
def lookup_toggle_active(request, key, pk):
    config = _get_config(key)
    if not config.has_is_active:
        raise Http404()
    obj = get_object_or_404(config.model, pk=pk)
    if request.method == "POST":
        obj.is_active = not obj.is_active
        obj.save(update_fields=["is_active"])
        messages.success(request, "وضعیت بروزرسانی شد.")
    return redirect("staff_dashboard:lookup_list", key=key)


@login_required
@platform_staff_required
def lookup_delete(request, key, pk):
    config = _get_config(key)
    obj = get_object_or_404(config.model, pk=pk)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "حذف شد.")
        except ProtectedError:
            messages.error(request, "این رکورد در جای دیگری استفاده شده و قابل حذف نیست.")
    return redirect("staff_dashboard:lookup_list", key=key)
