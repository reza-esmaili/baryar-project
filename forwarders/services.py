"""
مدارک ثبت‌نام شرکت حمل و احراز صلاحیت آن.

قانون تایید (تنها منبع این منطق): شرکت وقتی «تایید‌شده» است که برای هر مدرک
اجباریِ دسته‌های خدماتش (مدارک مشترک + مدارک هر دسته، که مدیر در داشبورد
تعریف می‌کند) دست‌کم یک نسخه‌ی تایید‌شده داشته باشد.
"""

from collections import OrderedDict

from django.db import transaction
from django.utils import timezone

from accounts.models import IdentityDocument

from .models import CompanyDocumentRequirement, ServiceCategory


def group_requirements(requirements):
    """
    ردیف‌های CompanyDocumentRequirement را بر اساس نوع مدرک گروه می‌کند (یک
    مدرک ممکن است برای چند دسته لازم باشد) → فهرستی از dict:
    {document_type, services, is_required, guidance}
    """
    grouped = OrderedDict()
    for req in requirements:
        item = grouped.setdefault(req.document_type_id, {
            "document_type": req.document_type,
            "services": [],
            "is_required": False,
            "guidance": "",
        })
        item["services"].append(req.service)
        item["is_required"] = item["is_required"] or req.is_required
        item["guidance"] = item["guidance"] or req.guidance
    return list(grouped.values())


def all_requirement_groups():
    """همه‌ی مدارک تعریف‌شده (برای فرم ثبت‌نام که دسته‌ها را همان‌جا انتخاب می‌کند)."""
    return group_requirements(
        CompanyDocumentRequirement.objects.filter(is_active=True, document_type__is_active=True)
        .select_related("document_type")
    )


def groups_for_categories(categories):
    return group_requirements(CompanyDocumentRequirement.for_categories(categories))


def latest_documents_by_type(company):
    """آخرین نسخه‌ی بارگذاری‌شده‌ی هر نوع مدرک شرکت."""
    latest = {}
    docs = company.identity_documents.filter(document_type__isnull=False).select_related("document_type")
    for doc in docs.order_by("created_at", "id"):
        latest[doc.document_type_id] = doc
    return latest


def document_checklist(company):
    """
    برای نمایش به شرکت و کارشناس: هر مدرکِ لازم برای دسته‌های فعلی شرکت به
    همراه آخرین نسخه‌ی ارسالی و وضعیتش.
    """
    latest = latest_documents_by_type(company)
    checklist = []
    for group in groups_for_categories(company.active_service_categories()):
        doc = latest.get(group["document_type"].id)
        checklist.append({**group, "document": doc, "status": doc.status if doc else None})
    return checklist


def missing_required_documents(company):
    """مدارک اجباری‌ای که هنوز نسخه‌ی قابل‌قبول (در انتظار یا تایید‌شده) ندارند."""
    return [
        item for item in document_checklist(company)
        if item["is_required"] and item["status"] not in (IdentityDocument.Status.PENDING, IdentityDocument.Status.APPROVED)
    ]


def is_company_fully_documented(company):
    checklist = document_checklist(company)
    required = [item for item in checklist if item["is_required"]]
    if required:
        return all(item["status"] == IdentityDocument.Status.APPROVED for item in required)
    # اگر مدیر هیچ مدرک اجباری تعریف نکرده، رفتار قبلی: همه‌ی مدارک ارسالی تایید شده باشند
    docs = company.identity_documents.all()
    return docs.exists() and not docs.exclude(status=IdentityDocument.Status.APPROVED).exists()


def recompute_company_verification(company):
    """
    is_verified را با وضعیت مدارک همگام می‌کند و True برمی‌گرداند اگر شرکت
    همین حالا تایید شد (برای ارسال اعلان «حساب شما تایید شد»).
    """
    verified = is_company_fully_documented(company)
    if company.is_verified == verified:
        return False
    company.is_verified = verified
    fields = ["is_verified", "updated_at"]
    if verified and not company.is_active:
        # ارسال مدارک شرکت را غیرفعال می‌کند؛ تایید کامل آن را دوباره فعال می‌کند.
        company.is_active = True
        fields.append("is_active")
    company.save(update_fields=fields)
    return verified


def registration_state(company):
    """
    وضعیت ثبت‌نام برای صف بررسی کارشناس:
    verified / inactive (تایید‌شده ولی غیرفعال) / rejected / pending / incomplete
    """
    if company.is_verified:
        return "verified" if company.is_active else "inactive"
    statuses = [item["status"] for item in document_checklist(company)]
    if IdentityDocument.Status.REJECTED in statuses:
        return "rejected"
    if IdentityDocument.Status.PENDING in statuses:
        return "pending"
    return "incomplete"


REGISTRATION_STATE_LABELS = {
    "pending": "در انتظار بررسی",
    "rejected": "نیازمند اصلاح",
    "incomplete": "مدارک ناقص",
    "verified": "تایید و فعال",
    "inactive": "تایید‌شده، غیرفعال",
}


@transaction.atomic
def approve_registration(company):
    """تایید یک‌جای ثبت‌نام: همه‌ی مدارک در انتظار تایید و شرکت فعال می‌شود."""
    company.identity_documents.filter(status=IdentityDocument.Status.PENDING).update(
        status=IdentityDocument.Status.APPROVED, updated_at=timezone.now(),
    )
    company.is_verified = True
    company.is_active = True
    company.save(update_fields=["is_verified", "is_active", "updated_at"])
    notify_company(company, "company_verified")


@transaction.atomic
def reject_registration(company, reason):
    """رد ثبت‌نام: مدارک در انتظار با یادداشت رد می‌شوند تا شرکت اصلاح و دوباره ارسال کند."""
    company.identity_documents.filter(status=IdentityDocument.Status.PENDING).update(
        status=IdentityDocument.Status.REJECTED, admin_note=reason[:1000], updated_at=timezone.now(),
    )
    company.is_verified = False
    company.save(update_fields=["is_verified", "updated_at"])
    notify_company(company, "company_rejected", reason=reason)


def notify_company(company, event_code, **extra):
    """پیامک رویداد به ادمین شرکت (پس از commit تراکنش جاری، اگر باشد)."""
    from core.services.notifications.tasks import notify_task
    from core.services.notifications.utils import display_name

    admin_user = company.admin_user
    if not admin_user or not admin_user.mobile:
        return
    context = {
        "contact_name": display_name(admin_user),
        "company_name": company.company_name,
        **extra,
    }
    transaction.on_commit(lambda: notify_task.delay(event_code, admin_user.mobile, context))


SERVICE_CATEGORY_CHOICES = [
    (value, label) for value, label in ServiceCategory.choices if value != ServiceCategory.ALL
]
