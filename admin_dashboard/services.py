# admin_dashboard/services.py

from accounts.models import IdentityDocument


def recompute_company_verification(company):
    """
    is_verified یک شرکت فورواردر باید دقیقا معادل «همه‌ی مدارک هویتی‌اش
    تایید شده‌اند» باشد. این تابع تنها منبع واحد این منطق است — همان قانونی
    که قبلا فقط داخل ForwarderCompanyAdmin.save_model/save_related پیاده
    شده بود، با این تفاوت که اینجا بعد از هر تایید/رد تک‌مدرکی هم صدا زده
    می‌شود (بر خلاف اکشن گروهی قدیمی در accounts/admin.py که با
    queryset.update() این محاسبه را انجام نمی‌داد).
    """
    docs = company.identity_documents.all()
    if not docs.exists():
        return

    all_approved = all(doc.status == IdentityDocument.Status.APPROVED for doc in docs)
    if company.is_verified != all_approved:
        company.is_verified = all_approved
        company.save(update_fields=["is_verified"])
