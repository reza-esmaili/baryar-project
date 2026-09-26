# admin_dashboard/services.py

from forwarders import services as company_services


def recompute_company_verification(company):
    """
    همگام‌سازی تایید شرکت پس از بررسی تک‌مدرک؛ منطق اصلی در
    forwarders.services است (مدارک اجباری دسته‌های خدمات شرکت).
    اگر با همین بررسی شرکت تایید شد، به شرکت اطلاع داده می‌شود.
    """
    became_verified = company_services.recompute_company_verification(company)
    if became_verified:
        company_services.notify_company(company, "company_verified")
    return became_verified
