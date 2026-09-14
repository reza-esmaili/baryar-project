from django.core.files.storage import storages


def protected_storage():
    """
    محل ذخیره فایل‌های حساس (مدارک هویتی/سفارش) — طبق تنظیمات
    STORAGES["protected"] در settings.py، عمداً خارج از MEDIA_ROOT است تا
    هرگز زیر آدرس عمومی /media/ سرو نشود؛ تنها راه دسترسی، ویوهای
    محافظت‌شده در documents/views.py (serve_identity_document و مشابه)
    است که مالکیت را قبل از پاسخ‌دادن به فایل بررسی می‌کنند.

    این تابع عمداً به‌جای یک نمونه ساخته‌شده، به FileField پاس داده می‌شود:
    وقتی storage یک callable باشد، جنگو در مایگریشن‌ها فقط مسیر همین تابع
    را ذخیره می‌کند (نه مسیر مطلق دیسک)، پس مایگریشن روی هر ماشین دیگری هم
    قابل اجراست.
    """
    return storages["protected"]
