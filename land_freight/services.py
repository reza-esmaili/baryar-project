"""
منطق کسب‌وکار «اعلام بار» حمل زمینی.

چرخه: مشتری درخواست ثبت می‌کند → درخواست برای همه‌ی شرکت‌های واجد شرایط
ارسال می‌شود (LandRequestDispatch) → اولین شرکتی که بپذیرد برنده است. تضمین
«فقط یک برنده» با یک UPDATE شرطی (WHERE status='open') در سطح دیتابیس است، نه
با بررسی در پایتون، تا دو پذیرش هم‌زمان هرگز هر دو موفق نشوند.
"""

import logging

from django.db import transaction
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

from core.services.notifications.events import (
    LAND_REQUEST_ACCEPTED_CUSTOMER,
    LAND_REQUEST_NEW_FORWARDER,
)
from core.services.notifications.tasks import notify_task
from forwarders.models import ForwarderCompany
from orders.models import CustomerNotification, ForwarderNotification

from .models import (
    DispatchStatus,
    LandFreightRequest,
    LandRequestDispatch,
    LandRequestEvent,
    LandRequestStatus,
    LandServiceScope,
    SCOPE_COMPANY_FLAG,
)

logger = logging.getLogger(__name__)

PENDING_DISPATCH_STATUSES = (DispatchStatus.SENT, DispatchStatus.SEEN)


class LandRequestError(Exception):
    """خطایی که پیام آن مستقیماً به کاربر نمایش داده می‌شود."""


# ─── تطبیق و ارسال ───────────────────────────────────────────────────────────

def eligible_carriers(land_request):
    """
    شرکت‌های واجد شرایط دریافت یک درخواست:
    تایید‌شده و فعال + دسته‌ی حمل زمینی متناسب با حوزه + ناوگان درخواستی +
    حوزه‌ی جغرافیایی (درون‌شهری: همان شهر؛ بین‌المللی: کشور طرف خارجی، یا
    شرکتی که کشوری تعیین نکرده یعنی همه‌ی کشورها؛ برون‌شهری: کل ایران).
    """
    flag = SCOPE_COMPANY_FLAG[land_request.scope]
    companies = ForwarderCompany.objects.filter(
        is_verified=True,
        is_active=True,
        **{flag: True},
    ).filter(land_profile__vehicle_types=land_request.vehicle_type)

    if land_request.scope == LandServiceScope.INTRACITY:
        companies = companies.filter(land_profile__service_cities=land_request.origin_city)
    elif land_request.scope == LandServiceScope.INTERNATIONAL:
        companies = companies.filter(
            Q(land_profile__service_countries=land_request.foreign_country)
            | Q(land_profile__service_countries__isnull=True)
        )

    return companies.select_related("admin_user").distinct()


def _log(land_request, event_type, actor=None, note=""):
    LandRequestEvent.objects.create(request=land_request, actor=actor, event_type=event_type, note=note)


def _sms_context(land_request):
    return {
        "request_ref": land_request.reference,
        "scope": land_request.get_scope_display(),
        "origin": land_request.origin_display,
        "destination": land_request.destination_display,
        "vehicle": land_request.vehicle_type.name,
        "price": f"{int(land_request.proposed_price):,}",
        "pickup_date": land_request.pickup_date.isoformat(),
    }


def dispatch_request(land_request, actor=None):
    """
    درخواست را برای همه‌ی شرکت‌های واجد شرایط ارسال می‌کند و تعداد را
    برمی‌گرداند. در انتشار مجدد، ارسال‌های قبلی دوباره «ارسال شده» می‌شوند و
    شرکت‌هایی که تازه واجد شرایط شده‌اند هم اضافه می‌شوند.
    """
    now = timezone.now()
    companies = list(eligible_carriers(land_request))
    existing = {d.company_id: d for d in land_request.dispatches.all()}

    to_create, to_reset = [], []
    for company in companies:
        dispatch = existing.get(company.id)
        if dispatch is None:
            to_create.append(LandRequestDispatch(request=land_request, company=company, sent_at=now))
        else:
            dispatch.status = DispatchStatus.SENT
            dispatch.sent_at = now
            dispatch.seen_at = None
            dispatch.responded_at = None
            to_reset.append(dispatch)

    LandRequestDispatch.objects.bulk_create(to_create)
    if to_reset:
        LandRequestDispatch.objects.bulk_update(to_reset, ["status", "sent_at", "seen_at", "responded_at"])

    inbox_url = reverse("forwarder_panel:land_request_detail", args=[land_request.pk])
    ForwarderNotification.objects.bulk_create([
        ForwarderNotification(
            forwarder_company=company,
            notif_type=ForwarderNotification.NotifType.LAND_REQUEST,
            title=f"درخواست حمل زمینی جدید {land_request.reference}",
            subtitle=f"{land_request.origin_display} ← {land_request.destination_display} — "
                     f"{int(land_request.proposed_price):,} ریال",
            url=inbox_url,
        )
        for company in companies
    ])

    _log(land_request, LandRequestEvent.EventType.DISPATCHED, actor, f"ارسال به {len(companies)} شرکت واجد شرایط")

    context = _sms_context(land_request)
    mobiles = [c.admin_user.mobile for c in companies if c.admin_user and c.admin_user.mobile]

    def send_sms():
        for mobile in mobiles:
            notify_task.delay(LAND_REQUEST_NEW_FORWARDER, mobile, context)

    transaction.on_commit(send_sms)
    return len(companies)


@transaction.atomic
def publish_request(land_request, actor):
    """ثبت اولیه: درخواست ذخیره‌شده (وضعیت open) را ثبت و ارسال می‌کند."""
    _log(land_request, LandRequestEvent.EventType.CREATED, actor)
    return dispatch_request(land_request, actor)


# ─── پذیرش (اولین پذیرنده برنده است) ─────────────────────────────────────────

def accept_request(request_id, company, user, expected_price):
    """
    expected_price همان کرایه‌ای است که شرکت هنگام پذیرش روی صفحه دیده؛ اگر
    مشتری در این فاصله کرایه را تغییر داده باشد پذیرش رد می‌شود تا شرکت هرگز
    ناخواسته با قیمتی متفاوت متعهد نشود.
    """
    if not LandRequestDispatch.objects.filter(request_id=request_id, company=company).exists():
        raise LandRequestError("این درخواست برای شرکت شما ارسال نشده است.")

    now = timezone.now()
    with transaction.atomic():
        # UPDATE شرطی اولین دستور تراکنش است: قفل نوشتن مستقیم گرفته می‌شود و
        # از بین پذیرش‌های هم‌زمان فقط یکی سطر را از open به assigned می‌برد.
        won = LandFreightRequest.objects.filter(
            pk=request_id,
            status=LandRequestStatus.OPEN,
            expires_at__gt=now,
            proposed_price=expected_price,
        ).update(
            status=LandRequestStatus.ASSIGNED,
            assigned_company=company,
            assigned_by=user,
            assigned_at=now,
            agreed_price=F("proposed_price"),
            updated_at=now,
        )

        land_request = LandFreightRequest.objects.select_related("customer").get(pk=request_id)

        if not won:
            if land_request.assigned_company_id == company.id:
                raise LandRequestError("این درخواست قبلاً توسط شرکت شما پذیرفته شده است.")
            if land_request.status in (LandRequestStatus.ASSIGNED, LandRequestStatus.IN_TRANSIT,
                                       LandRequestStatus.DELIVERED):
                raise LandRequestError("متاسفانه این درخواست زودتر توسط شرکت دیگری پذیرفته شد.")
            if land_request.status == LandRequestStatus.CANCELLED:
                raise LandRequestError("این درخواست توسط مشتری لغو شده است.")
            if land_request.status == LandRequestStatus.OPEN and land_request.expires_at > now:
                raise LandRequestError("کرایه‌ی این درخواست توسط مشتری تغییر کرده است؛ صفحه را دوباره بارگذاری و مبلغ جدید را بررسی کنید.")
            raise LandRequestError("مهلت پذیرش این درخواست به پایان رسیده است.")

        LandRequestDispatch.objects.filter(request_id=request_id, company=company).update(
            status=DispatchStatus.ACCEPTED, responded_at=now,
        )
        LandRequestDispatch.objects.filter(
            request_id=request_id, status__in=PENDING_DISPATCH_STATUSES,
        ).exclude(company=company).update(status=DispatchStatus.MISSED, responded_at=now)

        _log(land_request, LandRequestEvent.EventType.ACCEPTED, user, f"پذیرفته شده توسط {company.company_name}")

        CustomerNotification.objects.create(
            user=land_request.customer,
            notif_type=CustomerNotification.NotifType.LAND_REQUEST,
            title=f"درخواست {land_request.reference} پذیرفته شد",
            subtitle=f"شرکت حمل: {company.company_name}",
            url=reverse("land_freight:request_detail", args=[land_request.pk]),
        )

        customer_mobile = land_request.customer.mobile
        sms_context = {
            "request_ref": land_request.reference,
            "company_name": company.company_name,
            "company_phone": company.phone,
        }
        transaction.on_commit(
            lambda: notify_task.delay(LAND_REQUEST_ACCEPTED_CUSTOMER, customer_mobile, sms_context)
        )

    return land_request


def mark_seen(land_request, company):
    LandRequestDispatch.objects.filter(
        request=land_request, company=company, status=DispatchStatus.SENT,
    ).update(status=DispatchStatus.SEEN, seen_at=timezone.now())


# ─── پیگیری بعد از پذیرش ─────────────────────────────────────────────────────

ALLOWED_CARRIER_TRANSITIONS = {
    LandRequestStatus.ASSIGNED: (LandRequestStatus.IN_TRANSIT, LandRequestStatus.DELIVERED),
    LandRequestStatus.IN_TRANSIT: (LandRequestStatus.DELIVERED,),
}


@transaction.atomic
def update_carrier_status(land_request, company, user, new_status):
    if land_request.assigned_company_id != company.id:
        raise LandRequestError("این درخواست به شرکت شما تعلق ندارد.")
    if new_status not in ALLOWED_CARRIER_TRANSITIONS.get(land_request.status, ()):
        raise LandRequestError("این تغییر وضعیت در مرحله‌ی فعلی درخواست مجاز نیست.")

    old_label = land_request.get_status_display()
    land_request.status = new_status
    land_request.save(update_fields=["status", "updated_at"])
    _log(
        land_request, LandRequestEvent.EventType.STATUS_CHANGED, user,
        f"{old_label} ← {land_request.get_status_display()}",
    )
    CustomerNotification.objects.create(
        user=land_request.customer,
        notif_type=CustomerNotification.NotifType.LAND_REQUEST,
        title=f"وضعیت درخواست {land_request.reference}: {land_request.get_status_display()}",
        subtitle=company.company_name,
        url=reverse("land_freight:request_detail", args=[land_request.pk]),
    )


# ─── اقدامات مشتری ───────────────────────────────────────────────────────────

CUSTOMER_CANCELLABLE_STATUSES = (LandRequestStatus.OPEN, LandRequestStatus.ASSIGNED, LandRequestStatus.EXPIRED)


@transaction.atomic
def cancel_request(land_request, user, reason=""):
    locked = LandFreightRequest.objects.select_for_update().get(pk=land_request.pk)
    if locked.status not in CUSTOMER_CANCELLABLE_STATUSES:
        raise LandRequestError("این درخواست در وضعیت فعلی قابل لغو نیست.")

    now = timezone.now()
    was_assigned_to = locked.assigned_company if locked.status == LandRequestStatus.ASSIGNED else None

    locked.status = LandRequestStatus.CANCELLED
    locked.cancelled_at = now
    locked.cancel_reason = reason[:255]
    locked.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])

    locked.dispatches.filter(status__in=PENDING_DISPATCH_STATUSES).update(
        status=DispatchStatus.CLOSED, responded_at=now,
    )
    _log(locked, LandRequestEvent.EventType.CANCELLED, user, reason)

    if was_assigned_to:
        ForwarderNotification.objects.create(
            forwarder_company=was_assigned_to,
            notif_type=ForwarderNotification.NotifType.LAND_REQUEST,
            title=f"درخواست {locked.reference} توسط مشتری لغو شد",
            subtitle=reason[:255],
            url=reverse("forwarder_panel:land_request_detail", args=[locked.pk]),
        )
    return locked


@transaction.atomic
def republish_request(land_request, user, new_price):
    """
    تغییر کرایه‌ی پیشنهادی و انتشار دوباره: برای درخواست باز (افزایش/کاهش
    کرایه) یا منقضی‌شده (شروع دوباره‌ی مهلت). ارسال‌ها دوباره فعال می‌شوند.
    """
    locked = LandFreightRequest.objects.select_for_update().get(pk=land_request.pk)
    if locked.status not in (LandRequestStatus.OPEN, LandRequestStatus.EXPIRED):
        raise LandRequestError("فقط درخواست‌های باز یا منقضی‌شده را می‌توان دوباره منتشر کرد.")
    if new_price is None or new_price <= 0:
        raise LandRequestError("کرایه‌ی پیشنهادی باید بیشتر از صفر باشد.")

    old_price = locked.proposed_price
    locked.proposed_price = new_price
    locked.status = LandRequestStatus.OPEN
    locked.expires_at = LandFreightRequest.default_expiry(locked.scope)
    locked.save(update_fields=["proposed_price", "status", "expires_at", "updated_at"])

    _log(
        locked, LandRequestEvent.EventType.REPUBLISHED, user,
        f"کرایه از {int(old_price):,} به {int(new_price):,} ریال تغییر کرد",
    )
    return dispatch_request(locked, user)


# ─── انقضا ───────────────────────────────────────────────────────────────────

def expire_stale_requests():
    """
    درخواست‌های بازی که مهلتشان گذشته را منقضی می‌کند. هم به‌صورت تنبل در
    صفحات فهرست فراخوانی می‌شود و هم با دستور مدیریتی expire_land_requests
    (برای cron یا Celery beat)، پس نیازی به زمان‌بند اجباری نیست.
    """
    now = timezone.now()
    stale_ids = list(
        LandFreightRequest.objects.filter(status=LandRequestStatus.OPEN, expires_at__lte=now)
        .values_list("pk", flat=True)
    )
    if not stale_ids:
        return 0

    expired = 0
    for pk in stale_ids:
        with transaction.atomic():
            changed = LandFreightRequest.objects.filter(
                pk=pk, status=LandRequestStatus.OPEN, expires_at__lte=now,
            ).update(status=LandRequestStatus.EXPIRED, updated_at=now)
            if not changed:
                continue
            land_request = LandFreightRequest.objects.select_related("customer").get(pk=pk)
            land_request.dispatches.filter(status__in=PENDING_DISPATCH_STATUSES).update(
                status=DispatchStatus.CLOSED, responded_at=now,
            )
            _log(land_request, LandRequestEvent.EventType.EXPIRED, None, "هیچ شرکتی در مهلت تعیین‌شده نپذیرفت")
            CustomerNotification.objects.create(
                user=land_request.customer,
                notif_type=CustomerNotification.NotifType.LAND_REQUEST,
                title=f"مهلت درخواست {land_request.reference} به پایان رسید",
                subtitle="می‌توانید با کرایه‌ی جدید دوباره منتشرش کنید.",
                url=reverse("land_freight:request_detail", args=[land_request.pk]),
            )
            expired += 1
    return expired
