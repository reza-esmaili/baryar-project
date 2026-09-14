# admin_dashboard/views_sms.py

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from core.models import SmsEvent, SmsLog, SmsProviderConfig
from core.services.notifications.events import NOTIFICATION_EVENTS

from .decorators import platform_staff_required
from .forms import SmsEventForm, SmsProviderConfigForm


@login_required
@platform_staff_required
def sms_provider_settings(request):
    config = SmsProviderConfig.objects.filter(is_active=True).first() or SmsProviderConfig.objects.first()

    if request.method == "POST":
        form = SmsProviderConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "تنظیمات سامانه پیامکی با موفقیت ذخیره شد.")
            return redirect("staff_dashboard:sms_provider_settings")
    else:
        form = SmsProviderConfigForm(instance=config)

    context = {"form": form, "config": config}
    return render(request, "admin_dashboard/sms_settings.html", context)


@login_required
@platform_staff_required
def sms_event_list(request):
    events = SmsEvent.objects.all().order_by("label")
    context = {"events": events}
    return render(request, "admin_dashboard/sms_event_list.html", context)


@login_required
@platform_staff_required
def sms_event_form(request, code):
    event = get_object_or_404(SmsEvent, code=code)
    event_meta = NOTIFICATION_EVENTS.get(code, {})

    if request.method == "POST":
        form = SmsEventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "تنظیمات رویداد با موفقیت ذخیره شد.")
            return redirect("staff_dashboard:sms_event_list")
    else:
        form = SmsEventForm(instance=event)

    param_fields = [
        (key, label, form[f"param_map__{key}"], "{%s}" % key)
        for key, label in event_meta.get("params", {}).items()
    ]
    param_list = [
        (key, label, "{%s}" % key)
        for key, label in event_meta.get("params", {}).items()
    ]

    context = {
        "form": form,
        "event": event,
        "param_list": param_list,
        "param_fields": param_fields,
    }
    return render(request, "admin_dashboard/sms_event_form.html", context)


@login_required
@platform_staff_required
def sms_log_list(request):
    logs = SmsLog.objects.all().order_by("-created_at")
    paginator = Paginator(logs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    context = {"page_obj": page_obj}
    return render(request, "admin_dashboard/sms_log_list.html", context)
