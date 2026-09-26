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
    LAND_DOCUMENT_REVIEWED,
    LAND_REQUEST_ACCEPTED_CUSTOMER,
    LAND_REQUEST_CANCELLED_FORWARDER,
    LAND_REQUEST_CREATED_CUSTOMER,
    LAND_REQUEST_EXPIRED_CUSTOMER,
    LAND_REQUEST_NEW_FORWARDER,
    LAND_REQUEST_STATUS_CUSTOMER,
)
from core.services.notifications.tasks import notify_task
from core.services.notifications.utils import display_name
from documents.models import DocumentRule
from forwarders.models import ForwarderCompany
from orders.models import CustomerNotification, ForwarderNotification
from rates.models import TransportMode

from .models import (
    OPEN_DISPATCH_STATUSES,
    DispatchStatus,
    LandDocumentStatus,
    LandFreightRequest,
    LandRequestDispatch,
    LandRequestDocument,
    LandRequestEvent,
    LandRequestStatus,
    LandServiceScope,
    SCOPE_COMPANY_FLAG,
)

logger = logging.getLogger(__name__)


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
            # با کرایه‌ی جدید، شرکتی که قبلاً رد کرده دوباره فرصت تصمیم دارد.
            dispatch.decline_reason = ""
            to_reset.append(dispatch)

    LandRequestDispatch.objects.bulk_create(to_create)
    if to_reset:
        LandRequestDispatch.objects.bulk_update(
            to_reset, ["status", "sent_at", "seen_at", "responded_at", "decline_reason"],
        )

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

    base_context = _sms_context(land_request)
    recipients = [
        (c.admin_user.mobile, {**base_context, "company_name": c.company_name})
        for c in companies if c.admin_user and c.admin_user.mobile
    ]

    def send_sms():
        for mobile, context in recipients:
            notify_task.delay(LAND_REQUEST_NEW_FORWARDER, mobile, context)

    transaction.on_commit(send_sms)
    return len(companies)


@transaction.atomic
def publish_request(land_request, actor):
    """ثبت اولیه: درخواست ذخیره‌شده (وضعیت open) را ثبت، مدارکش را آماده و ارسال می‌کند."""
    _log(land_request, LandRequestEvent.EventType.CREATED, actor)
    sync_land_documents(land_request)
    carriers = dispatch_request(land_request, actor)

    customer = land_request.customer
    context = {
        "customer_name": display_name(customer),
        "request_ref": land_request.reference,
        "carriers_count": carriers,
    }
    transaction.on_commit(lambda: notify_task.delay(LAND_REQUEST_CREATED_CUSTOMER, customer.mobile, context))
    return carriers


# ─── پذیرش (اولین پذیرنده برنده است) ─────────────────────────────────────────

def accept_request(request_id, company, user, expected_price):
    """
    expected_price همان کرایه‌ای است که شرکت هنگام پذیرش روی صفحه دیده؛ اگر
    مشتری در این فاصله کرایه را تغییر داده باشد پذیرش رد می‌شود تا شرکت هرگز
    ناخواسته با قیمتی متفاوت متعهد نشود.
    """
    dispatch = LandRequestDispatch.objects.filter(request_id=request_id, company=company).first()
    if dispatch is None:
        raise LandRequestError("این درخواست برای شرکت شما ارسال نشده است.")
    if dispatch.status == DispatchStatus.DECLINED:
        raise LandRequestError("شرکت شما این درخواست را رد کرده است.")

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
            request_id=request_id, status__in=OPEN_DISPATCH_STATUSES,
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
            "customer_name": display_name(land_request.customer),
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


def decline_request(land_request, company, reason=""):
    """
    شرکت درخواست را نمی‌پذیرد: فقط از صندوق همان شرکت حذف می‌شود و برای
    بقیه‌ی شرکت‌ها باز می‌ماند. دلیل برای گزارش مدیر ثبت می‌شود.
    """
    if land_request.status != LandRequestStatus.OPEN:
        raise LandRequestError("این درخواست دیگر باز نیست.")
    updated = LandRequestDispatch.objects.filter(
        request=land_request, company=company, status__in=OPEN_DISPATCH_STATUSES,
    ).update(status=DispatchStatus.DECLINED, responded_at=timezone.now(), decline_reason=reason.strip()[:255])
    if not updated:
        raise LandRequestError("این درخواست در صندوق باز شرکت شما نیست.")
    # عمداً در تاریخچه‌ی درخواست ثبت نمی‌شود: آن تاریخچه را مشتری و شرکت برنده
    # می‌بینند و تصمیم رقبا نباید به آن‌ها نشان داده شود؛ دلیل در خودِ ارسال می‌ماند.


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
    customer = land_request.customer
    context = {
        "customer_name": display_name(customer),
        "request_ref": land_request.reference,
        "status": land_request.get_status_display(),
        "company_name": company.company_name,
    }
    transaction.on_commit(lambda: notify_task.delay(LAND_REQUEST_STATUS_CUSTOMER, customer.mobile, context))


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

    locked.dispatches.filter(status__in=OPEN_DISPATCH_STATUSES).update(
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
        admin_user = was_assigned_to.admin_user
        if admin_user and admin_user.mobile:
            context = {
                "company_name": was_assigned_to.company_name,
                "request_ref": locked.reference,
                "reason": reason or "ذکر نشده",
            }
            transaction.on_commit(
                lambda: notify_task.delay(LAND_REQUEST_CANCELLED_FORWARDER, admin_user.mobile, context)
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
            land_request.dispatches.filter(status__in=OPEN_DISPATCH_STATUSES).update(
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
            customer = land_request.customer
            context = {"customer_name": display_name(customer), "request_ref": land_request.reference}
            transaction.on_commit(
                lambda mobile=customer.mobile, ctx=context: notify_task.delay(
                    LAND_REQUEST_EXPIRED_CUSTOMER, mobile, ctx,
                )
            )
            expired += 1
    return expired


# ─── مدارک محموله ─────────────────────────────────────────────────────────────
#
# همان قوانین مدارک (DocumentRule) که برای سفارش‌های هوایی/دریایی استفاده
# می‌شوند؛ قانونی برای درخواست زمینی اعمال می‌شود که روش حمل آن «زمینی» باشد و
# (در صورت تعیین) حوزه، کالا، مبدا و کشور/شهر/مرز طرف خارجی هم بخواند.

def land_rule_matches(rule, land_request):
    if rule.transport_mode != TransportMode.LAND:
        return False
    if rule.land_scope and rule.land_scope != land_request.scope:
        return False
    # درخواست زمینی رویه‌ی ارسال و زیردسته‌ی کالا ندارد
    if rule.shipping_procedure or rule.cargo_subcategory_id:
        return False
    if rule.cargo_type_id and rule.cargo_type_id != land_request.cargo_type_id:
        return False

    iran_origin = land_request.origin_city
    if rule.origin_city_id and (not iran_origin or rule.origin_city_id != iran_origin.pk):
        return False
    if rule.origin_province_id and (not iran_origin or rule.origin_province_id != iran_origin.province_id):
        return False

    is_international = land_request.scope == LandServiceScope.INTERNATIONAL
    if rule.destination_country_id and (not is_international or rule.destination_country_id != land_request.foreign_country_id):
        return False
    if rule.destination_city_id and (not is_international or rule.destination_city_id != land_request.foreign_city_id):
        return False
    if rule.destination_port_id and rule.destination_port_id != land_request.border_crossing_id:
        return False
    return True


def required_land_document_rules(land_request):
    """{document_type_id: مهم‌ترین قانونِ منطبق} — هر نوع مدرک یک‌بار."""
    rules = DocumentRule.objects.filter(
        is_active=True, document_type__is_active=True, transport_mode=TransportMode.LAND,
    ).select_related("document_type")

    best = {}
    for rule in rules:
        if not land_rule_matches(rule, land_request):
            continue
        current = best.get(rule.document_type_id)
        if current is None or rule.specificity_score + rule.priority > current.specificity_score + current.priority:
            best[rule.document_type_id] = rule
    return best


@transaction.atomic
def sync_land_documents(land_request):
    """مدارک لازم را می‌سازد؛ مدارکی که دیگر لازم نیستند اگر فایل ندارند حذف می‌شوند."""
    rules = required_land_document_rules(land_request)
    for document_type_id, rule in rules.items():
        doc, created = LandRequestDocument.objects.get_or_create(
            request=land_request, document_type_id=document_type_id,
            defaults={"source_rule": rule, "is_required": rule.is_required},
        )
        if not created and (doc.source_rule_id != rule.pk or doc.is_required != rule.is_required):
            doc.source_rule = rule
            doc.is_required = rule.is_required
            doc.save(update_fields=["source_rule", "is_required", "updated_at"])

    stale = land_request.documents.exclude(document_type_id__in=rules.keys())
    stale.filter(file="").delete()
    stale.exclude(file="").filter(is_required=True).update(is_required=False)
    return list(land_request.documents.select_related("document_type", "source_rule"))


def land_documents_summary(land_request):
    docs = list(land_request.documents.all())
    required = [d for d in docs if d.is_required]
    return {
        "total": len(docs),
        "required": len(required),
        "missing": sum(1 for d in required if d.status in (LandDocumentStatus.PENDING_UPLOAD, LandDocumentStatus.REJECTED)),
        "approved": sum(1 for d in docs if d.status == LandDocumentStatus.APPROVED),
    }


def validate_document_file(document_type, uploaded):
    ext = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
    allowed = document_type.get_allowed_extensions_list()
    if allowed and ext not in allowed:
        raise LandRequestError(f"فرمت فایل مجاز نیست. فرمت‌های مجاز: {', '.join(allowed)}")
    if uploaded.size > document_type.max_file_size_mb * 1024 * 1024:
        raise LandRequestError(f"حجم فایل نباید بیشتر از {document_type.max_file_size_mb} مگابایت باشد.")


UPLOADABLE_REQUEST_STATUSES = (LandRequestStatus.OPEN, LandRequestStatus.ASSIGNED, LandRequestStatus.IN_TRANSIT)


@transaction.atomic
def upload_land_document(document, uploaded, user):
    land_request = document.request
    if land_request.status not in UPLOADABLE_REQUEST_STATUSES:
        raise LandRequestError("در وضعیت فعلی درخواست امکان بارگذاری مدرک وجود ندارد.")
    if document.status == LandDocumentStatus.APPROVED:
        raise LandRequestError("این مدرک تایید شده و نیازی به بارگذاری دوباره ندارد.")
    validate_document_file(document.document_type, uploaded)

    replaced_file = document.file.name if document.file else ""
    document.file = uploaded
    document.status = LandDocumentStatus.UPLOADED
    document.uploaded_by = user
    document.uploaded_at = timezone.now()
    document.rejection_reason = ""
    document.save()
    if replaced_file and replaced_file != document.file.name:
        # نسخه‌ی قبلی (معمولاً ردشده) دیگر به جایی ارجاع ندارد؛ پس از commit پاک می‌شود
        storage = document.file.storage
        transaction.on_commit(lambda: storage.delete(replaced_file))

    _log(land_request, LandRequestEvent.EventType.DOCUMENT_UPLOADED, user, document.document_type.title)
    if land_request.assigned_company_id:
        ForwarderNotification.objects.create(
            forwarder_company_id=land_request.assigned_company_id,
            notif_type=ForwarderNotification.NotifType.DOC_UPLOAD,
            title=f"مدرک «{document.document_type.title}» برای {land_request.reference} بارگذاری شد",
            subtitle="برای بررسی به جزئیات درخواست مراجعه کنید.",
            url=reverse("forwarder_panel:land_request_detail", args=[land_request.pk]),
        )


@transaction.atomic
def review_land_document(document, company, user, approve, reason=""):
    land_request = document.request
    if land_request.assigned_company_id != company.id:
        raise LandRequestError("فقط شرکت پذیرنده‌ی این درخواست می‌تواند مدارک را بررسی کند.")
    if document.status != LandDocumentStatus.UPLOADED:
        raise LandRequestError("این مدرک در وضعیت قابل بررسی نیست.")
    if not approve and not reason.strip():
        raise LandRequestError("برای رد مدرک، دلیل آن را بنویسید تا مشتری اصلاح کند.")

    document.status = LandDocumentStatus.APPROVED if approve else LandDocumentStatus.REJECTED
    document.rejection_reason = "" if approve else reason.strip()[:255]
    document.reviewed_by = user
    document.reviewed_at = timezone.now()
    document.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"])

    result = "تایید شد" if approve else "رد شد"
    _log(land_request, LandRequestEvent.EventType.DOCUMENT_REVIEWED, user,
         f"{document.document_type.title}: {result}" + (f" — {document.rejection_reason}" if not approve else ""))
    CustomerNotification.objects.create(
        user=land_request.customer,
        notif_type=CustomerNotification.NotifType.LAND_REQUEST,
        title=f"مدرک «{document.document_type.title}» {result}",
        subtitle=document.rejection_reason or land_request.reference,
        url=reverse("land_freight:request_detail", args=[land_request.pk]),
    )
    customer = land_request.customer
    context = {
        "customer_name": display_name(customer),
        "request_ref": land_request.reference,
        "doc_title": document.document_type.title,
        "result": result,
        "reason": document.rejection_reason or "-",
    }
    transaction.on_commit(lambda: notify_task.delay(LAND_DOCUMENT_REVIEWED, customer.mobile, context))
