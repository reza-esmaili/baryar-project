# admin_dashboard/views_sms.py
#
# بخش «پیامک» داشبورد مدیریت: تعریف و ویرایش سامانه‌های پیامکی (فقط یکی در هر
# لحظه فعال است و همه‌ی ارسال‌ها از همان انجام می‌شود)، تنظیم رویدادهای پیامکی
# (فعال/غیرفعال، متن با متغیرهای پویا یا قالب sms.ir) و لاگ ارسال‌ها.

import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import SmsEvent, SmsLog, SmsProviderConfig
from core.services.notifications.events import (
    DEFAULT_TEXTS,
    GROUP_ORDER,
    NOTIFICATION_EVENTS,
    SAMPLE_VALUES,
    get_event_params,
    render_sample,
)
from core.services.notifications.sms import build_provider

from .decorators import platform_staff_required
from .forms import SmsEventForm, SmsProviderConfigForm

MOBILE_RE = re.compile(r"^09\d{9}$")


# ─── سامانه‌های پیامکی ────────────────────────────────────────────────────────

@login_required
@platform_staff_required
def sms_provider_settings(request):
    providers = SmsProviderConfig.objects.all()
    active = next((p for p in providers if p.is_active), None)
    return render(request, "admin_dashboard/sms_settings.html", {
        "providers": providers,
        "active_provider": active,
        "enabled_events": SmsEvent.objects.filter(is_enabled=True).count(),
        "total_events": SmsEvent.objects.count(),
    })


@login_required
@platform_staff_required
def sms_provider_form(request, pk=None):
    provider = get_object_or_404(SmsProviderConfig, pk=pk) if pk else None

    if request.method == "POST":
        form = SmsProviderConfigForm(request.POST, instance=provider)
        if form.is_valid():
            saved = form.save()
            messages.success(request, f"سامانه‌ی «{saved.name}» ذخیره شد.")
            return redirect("staff_dashboard:sms_provider_settings")
    else:
        form = SmsProviderConfigForm(instance=provider, initial=None if provider else {
            "is_active": not SmsProviderConfig.objects.filter(is_active=True).exists(),
        })

    return render(request, "admin_dashboard/sms_provider_form.html", {"form": form, "provider": provider})


@login_required
@platform_staff_required
@require_POST
def sms_provider_activate(request, pk):
    provider = get_object_or_404(SmsProviderConfig, pk=pk)
    provider.is_active = True
    provider.save()  # save() بقیه‌ی سامانه‌ها را غیرفعال می‌کند
    messages.success(request, f"از این پس همه‌ی پیامک‌ها از «{provider.name}» ارسال می‌شوند.")
    return redirect("staff_dashboard:sms_provider_settings")


@login_required
@platform_staff_required
@require_POST
def sms_provider_delete(request, pk):
    provider = get_object_or_404(SmsProviderConfig, pk=pk)
    if provider.is_active:
        messages.error(request, "سامانه‌ی فعال را نمی‌توان حذف کرد؛ ابتدا سامانه‌ی دیگری را فعال کنید.")
    else:
        name = provider.name
        provider.delete()
        messages.success(request, f"سامانه‌ی «{name}» حذف شد.")
    return redirect("staff_dashboard:sms_provider_settings")


@login_required
@platform_staff_required
@require_POST
def sms_provider_test(request, pk):
    """ارسال پیامک آزمایشی یا استعلام اعتبار با همین سامانه (حتی اگر فعال نباشد)."""
    provider = get_object_or_404(SmsProviderConfig, pk=pk)

    if request.POST.get("action") == "credit":
        try:
            result = build_provider(provider).get_credit()
            credit = result.get("data") if isinstance(result, dict) else result
            messages.success(request, f"اتصال به «{provider.name}» برقرار است. اعتبار باقی‌مانده: {credit}")
        except Exception as exc:  # خطای شبکه/SDK نباید صفحه‌ی مدیریت را بشکند
            messages.error(request, f"خطا در ارتباط با «{provider.name}»: {exc}")
        return redirect("staff_dashboard:sms_provider_settings")

    mobile = request.POST.get("mobile", "").strip()
    if not MOBILE_RE.match(mobile):
        messages.error(request, "شماره موبایل آزمایشی باید ۱۱ رقم و با ۰۹ شروع شود.")
        return redirect("staff_dashboard:sms_provider_settings")

    text = request.POST.get("message", "").strip() or "پیامک آزمایشی باریار — اتصال سامانه‌ی پیامکی برقرار است."
    log = SmsLog.objects.create(
        mobile=mobile, template_key="provider_test",
        parameters={"provider": provider.name, "message": text}, status="pending",
    )
    try:
        log.response_data = build_provider(provider).send_text(mobile=mobile, message=text)
        log.status = "sent"
        log.save(update_fields=["status", "response_data"])
        messages.success(request, f"پیامک آزمایشی از «{provider.name}» به {mobile} ارسال شد.")
    except Exception as exc:  # SMSIRException یا خطای شبکه/SDK
        log.status, log.error_message = "failed", str(exc)
        log.save(update_fields=["status", "error_message"])
        messages.error(request, f"ارسال پیامک آزمایشی ناموفق بود: {exc}")
    return redirect("staff_dashboard:sms_provider_settings")


# ─── رویدادهای پیامکی ─────────────────────────────────────────────────────────

def _event_rows():
    """رویدادهای ثبت‌شده، گروه‌بندی‌شده به ترتیب رجیستری، با پیش‌نمایش متن."""
    events = {event.code: event for event in SmsEvent.objects.all()}
    groups = {name: [] for name in GROUP_ORDER}
    for code, meta in NOTIFICATION_EVENTS.items():
        event = events.pop(code, None)
        if event is None:
            continue
        groups.setdefault(meta["group"], []).append({
            "event": event,
            "recipient": meta["recipient"],
            "params": meta["params"],
            "preview": render_sample(event.custom_text, code) if event.custom_text else "",
        })
    # رویدادهایی که دیگر در کد تعریف نیستند (قدیمی) هم نمایش داده می‌شوند تا قابل غیرفعال‌سازی باشند.
    if events:
        groups["سایر"] = [
            {"event": event, "recipient": "—", "params": {}, "preview": event.custom_text}
            for event in events.values()
        ]
    return [(name, rows) for name, rows in groups.items() if rows]


@login_required
@platform_staff_required
def sms_event_list(request):
    return render(request, "admin_dashboard/sms_event_list.html", {
        "groups": _event_rows(),
        "has_active_provider": SmsProviderConfig.objects.filter(is_active=True).exists(),
    })


@login_required
@platform_staff_required
@require_POST
def sms_event_toggle(request, code):
    event = get_object_or_404(SmsEvent, code=code)
    event.is_enabled = not event.is_enabled
    event.save(update_fields=["is_enabled", "updated_at"])
    state = "فعال" if event.is_enabled else "غیرفعال"
    messages.success(request, f"ارسال پیامک رویداد «{event.label}» {state} شد.")
    return redirect(f"{reverse('staff_dashboard:sms_event_list')}#event-{event.code}")


@login_required
@platform_staff_required
def sms_event_form(request, code):
    event = get_object_or_404(SmsEvent, code=code)
    event_meta = NOTIFICATION_EVENTS.get(code, {})

    if request.method == "POST" and request.POST.get("action") == "restore_default":
        if code in DEFAULT_TEXTS:
            event.custom_text = DEFAULT_TEXTS[code]
            event.save(update_fields=["custom_text", "updated_at"])
            messages.success(request, "متن پیش‌فرض رویداد بازگردانده شد.")
        return redirect("staff_dashboard:sms_event_edit", code=code)

    if request.method == "POST":
        form = SmsEventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "تنظیمات رویداد با موفقیت ذخیره شد.")
            return redirect("staff_dashboard:sms_event_list")
    else:
        form = SmsEventForm(instance=event)

    params = get_event_params(code)
    param_fields = [
        (key, label, form[f"param_map__{key}"], "{%s}" % key)
        for key, label in params.items()
    ]
    param_list = [
        (key, label, "{%s}" % key, SAMPLE_VALUES.get(key, f"[{label}]"))
        for key, label in params.items()
    ]

    context = {
        "form": form,
        "event": event,
        "event_meta": event_meta,
        "param_list": param_list,
        "param_fields": param_fields,
        "preview": render_sample(form["custom_text"].value() or "", code),
        "default_text": DEFAULT_TEXTS.get(code, ""),
        "sample_values": {key: SAMPLE_VALUES.get(key, f"[{label}]") for key, label in params.items()},
    }
    return render(request, "admin_dashboard/sms_event_form.html", context)


@login_required
@platform_staff_required
def sms_log_list(request):
    logs = SmsLog.objects.all().order_by("-created_at")
    status = request.GET.get("status", "").strip()
    if status in ("sent", "failed", "pending"):
        logs = logs.filter(status=status)
    event = request.GET.get("event", "").strip()
    if event:
        logs = logs.filter(template_key=event)
    q = request.GET.get("q", "").strip()
    if q:
        logs = logs.filter(mobile__icontains=q)

    paginator = Paginator(logs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    querystring = params.urlencode()
    context = {
        "page_obj": page_obj,
        "status": status,
        "event": event,
        "q": q,
        "event_choices": [(code, meta["label"]) for code, meta in NOTIFICATION_EVENTS.items()],
        "querystring": querystring + "&" if querystring else "",
    }
    return render(request, "admin_dashboard/sms_log_list.html", context)
