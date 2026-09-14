# core/services/notifications/events.py
#
# فهرست رویدادهای پیامکی پلتفرم. این‌جا فقط تعریف می‌شود که یک رویداد
# «چیست» و «چه پارامترهایی دارد» — محل واقعی رخ‌دادن هر رویداد در کد
# (ویوها/سرویس‌ها) است. تنظیم فعال/غیرفعال بودن، متن یا قالب هر رویداد در
# مدل core.models.SmsEvent نگهداری می‌شود (یک ردیف به‌ازای هر کد اینجا،
# با مهاجرت داده‌ای ساخته می‌شود).

OTP_VERIFICATION = "otp_verification"
ORDER_DRAFT_CREATED = "order_draft_created"
RATE_MATCH_FOUND_CUSTOMER = "rate_match_found_customer"
RATE_MATCH_FOUND_FORWARDER = "rate_match_found_forwarder"
ORDER_FINALIZED = "order_finalized"
ADDITIONAL_DOCUMENT_REQUESTED = "additional_document_requested"


NOTIFICATION_EVENTS = {
    OTP_VERIFICATION: {
        "label": "ارسال کد تایید (OTP)",
        "description": "هنگام ورود، ثبت‌نام یا فراموشی رمز عبور برای تایید شماره موبایل ارسال می‌شود.",
        "params": {
            "code": "کد تایید",
        },
    },
    ORDER_DRAFT_CREATED: {
        "label": "ثبت پیش‌نویس سفارش",
        "description": "وقتی مشتری نرخ را انتخاب می‌کند و درخواست به‌عنوان پیش‌نویس ثبت می‌شود.",
        "params": {
            "order_id": "شماره سفارش",
            "customer_name": "نام مشتری",
            "origin": "مبدا",
            "destination": "مقصد",
        },
    },
    RATE_MATCH_FOUND_CUSTOMER: {
        "label": "پیدا شدن تطبیق نرخ (به مشتری)",
        "description": "همزمان با ثبت پیش‌نویس، به مشتری اطلاع می‌دهد نرخش با کدام فورواردر تطبیق یافت.",
        "params": {
            "order_id": "شماره سفارش",
            "forwarder_name": "نام فورواردر",
        },
    },
    RATE_MATCH_FOUND_FORWARDER: {
        "label": "پیدا شدن تطبیق نرخ (به فورواردر)",
        "description": "به فورواردر/شعبه صاحب نرخ اطلاع می‌دهد یک درخواست جدید مطابق نرخش ثبت شده است.",
        "params": {
            "order_id": "شماره سفارش",
            "origin": "مبدا",
            "destination": "مقصد",
            "customer_name": "نام مشتری",
        },
    },
    ORDER_FINALIZED: {
        "label": "تکمیل نهایی سفارش (ایجاد بار)",
        "description": "وقتی مشتری اطلاعات و مدارک سفارش را کامل می‌کند و سفارش برای بررسی فورواردر ارسال می‌شود.",
        "params": {
            "order_id": "شماره سفارش",
            "final_price": "مبلغ نهایی",
        },
    },
    ADDITIONAL_DOCUMENT_REQUESTED: {
        "label": "درخواست مدرک تکمیلی دریافت شد",
        "description": "وقتی فورواردر از مشتری درخواست مدرک اضافه می‌کند، لینک آپلود برای مشتری پیامک می‌شود.",
        "params": {
            "order_id": "شماره سفارش",
            "doc_title": "عنوان مدرک",
            "link": "لینک آپلود",
        },
    },
}


def get_event_params(code):
    return NOTIFICATION_EVENTS.get(code, {}).get("params", {})
