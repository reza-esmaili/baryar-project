# core/services/notifications/events.py
#
# فهرست رویدادهای پیامکی پلتفرم. این‌جا فقط تعریف می‌شود که یک رویداد
# «چیست» و «چه متغیرهایی دارد» — محل واقعی رخ‌دادن هر رویداد در کد
# (ویوها/سرویس‌ها) است. فعال/غیرفعال بودن، متن یا قالب هر رویداد در مدل
# core.models.SmsEvent نگهداری می‌شود و از داشبورد مدیریت قابل ویرایش است.
#
# هر فراخوانی notify() باید همه‌ی متغیرهای رویدادش را در context بفرستد.

OTP_VERIFICATION = "otp_verification"
CUSTOMER_WELCOME = "customer_welcome"

ORDER_DRAFT_CREATED = "order_draft_created"
RATE_MATCH_FOUND_CUSTOMER = "rate_match_found_customer"
RATE_MATCH_FOUND_FORWARDER = "rate_match_found_forwarder"
ORDER_FINALIZED = "order_finalized"
ORDER_STATUS_CHANGED = "order_status_changed"
ORDER_DOCUMENT_REVIEWED = "order_document_reviewed"
ORDER_MESSAGE_TO_CUSTOMER = "order_message_to_customer"
ORDER_MESSAGE_TO_FORWARDER = "order_message_to_forwarder"
ADDITIONAL_DOCUMENT_REQUESTED = "additional_document_requested"
ADDITIONAL_DOCUMENT_UPLOADED = "additional_document_uploaded"

COMPANY_REGISTRATION_RECEIVED = "company_registration_received"
COMPANY_VERIFIED = "company_verified"
COMPANY_REJECTED = "company_rejected"
FORWARDER_STAFF_CREATED = "forwarder_staff_created"

LAND_REQUEST_CREATED_CUSTOMER = "land_request_created_customer"
LAND_REQUEST_NEW_FORWARDER = "land_request_new_forwarder"
LAND_REQUEST_ACCEPTED_CUSTOMER = "land_request_accepted_customer"
LAND_REQUEST_STATUS_CUSTOMER = "land_request_status_customer"
LAND_REQUEST_CANCELLED_FORWARDER = "land_request_cancelled_forwarder"
LAND_REQUEST_EXPIRED_CUSTOMER = "land_request_expired_customer"
LAND_DOCUMENT_REVIEWED = "land_document_reviewed"

TICKET_ANSWERED = "ticket_answered"


# دسته‌بندی برای نمایش گروهی در داشبورد
GROUP_ACCOUNT = "حساب کاربری"
GROUP_ORDERS = "سفارش‌های هوایی و دریایی"
GROUP_COMPANY = "شرکت‌های حمل"
GROUP_LAND = "حمل زمینی (اعلام بار)"
GROUP_SUPPORT = "پشتیبانی"

RECIPIENT_CUSTOMER = "مشتری"
RECIPIENT_COMPANY = "شرکت حمل"
RECIPIENT_USER = "کاربر"

NOTIFICATION_EVENTS = {
    OTP_VERIFICATION: {
        "group": GROUP_ACCOUNT, "recipient": RECIPIENT_USER,
        "label": "ارسال کد تایید (OTP)",
        "description": "هنگام ورود، ثبت‌نام یا فراموشی رمز عبور برای تایید شماره موبایل ارسال می‌شود.",
        "params": {"code": "کد تایید"},
    },
    CUSTOMER_WELCOME: {
        "group": GROUP_ACCOUNT, "recipient": RECIPIENT_CUSTOMER,
        "label": "خوش‌آمدگویی به مشتری جدید",
        "description": "بلافاصله پس از تکمیل ثبت‌نام مشتری.",
        "params": {"customer_name": "نام مشتری"},
    },

    ORDER_DRAFT_CREATED: {
        "group": GROUP_ORDERS, "recipient": RECIPIENT_CUSTOMER,
        "label": "ثبت پیش‌نویس سفارش",
        "description": "وقتی مشتری نرخ را انتخاب می‌کند و درخواست به‌عنوان پیش‌نویس ثبت می‌شود.",
        "params": {
            "customer_name": "نام مشتری", "order_id": "شماره سفارش",
            "origin": "مبدا", "destination": "مقصد",
        },
    },
    RATE_MATCH_FOUND_CUSTOMER: {
        "group": GROUP_ORDERS, "recipient": RECIPIENT_CUSTOMER,
        "label": "تطبیق نرخ (به مشتری)",
        "description": "همزمان با ثبت پیش‌نویس، به مشتری اطلاع می‌دهد سفارش به کدام شرکت سپرده شد.",
        "params": {"customer_name": "نام مشتری", "order_id": "شماره سفارش", "forwarder_name": "نام شرکت حمل"},
    },
    RATE_MATCH_FOUND_FORWARDER: {
        "group": GROUP_ORDERS, "recipient": RECIPIENT_COMPANY,
        "label": "سفارش جدید مطابق نرخ (به شرکت حمل)",
        "description": "به شرکت/شعبه‌ی صاحب نرخ اطلاع می‌دهد سفارش جدیدی مطابق نرخش ثبت شده است.",
        "params": {
            "company_name": "نام شرکت حمل", "order_id": "شماره سفارش", "customer_name": "نام مشتری",
            "origin": "مبدا", "destination": "مقصد",
        },
    },
    ORDER_FINALIZED: {
        "group": GROUP_ORDERS, "recipient": RECIPIENT_CUSTOMER,
        "label": "نهایی‌شدن سفارش",
        "description": "وقتی مشتری اطلاعات و مدارک را کامل می‌کند و سفارش برای شرکت حمل ارسال می‌شود.",
        "params": {
            "customer_name": "نام مشتری", "order_id": "شماره سفارش",
            "final_price": "مبلغ نهایی (ریال)", "forwarder_name": "نام شرکت حمل",
        },
    },
    ORDER_STATUS_CHANGED: {
        "group": GROUP_ORDERS, "recipient": RECIPIENT_CUSTOMER,
        "label": "تغییر وضعیت سفارش",
        "description": "وقتی شرکت حمل وضعیت سفارش را تغییر می‌دهد (تایید، رد، تکمیل و...).",
        "params": {
            "customer_name": "نام مشتری", "order_id": "شماره سفارش",
            "status": "وضعیت جدید", "forwarder_name": "نام شرکت حمل",
        },
    },
    ORDER_DOCUMENT_REVIEWED: {
        "group": GROUP_ORDERS, "recipient": RECIPIENT_CUSTOMER,
        "label": "بررسی مدرک سفارش",
        "description": "وقتی شرکت حمل یکی از مدارک سفارش را تایید یا رد می‌کند.",
        "params": {
            "customer_name": "نام مشتری", "order_id": "شماره سفارش", "doc_title": "عنوان مدرک",
            "result": "نتیجه (تایید شد/رد شد)", "reason": "توضیح",
        },
    },
    ORDER_MESSAGE_TO_CUSTOMER: {
        "group": GROUP_ORDERS, "recipient": RECIPIENT_CUSTOMER,
        "label": "پیام جدید شرکت حمل در سفارش",
        "description": "وقتی شرکت حمل در صفحه‌ی سفارش برای مشتری پیام می‌فرستد.",
        "params": {"customer_name": "نام مشتری", "order_id": "شماره سفارش", "forwarder_name": "نام شرکت حمل"},
    },
    ORDER_MESSAGE_TO_FORWARDER: {
        "group": GROUP_ORDERS, "recipient": RECIPIENT_COMPANY,
        "label": "پیام جدید مشتری در سفارش",
        "description": "وقتی مشتری در صفحه‌ی سفارش برای شرکت حمل پیام می‌فرستد.",
        "params": {"company_name": "نام شرکت حمل", "order_id": "شماره سفارش", "customer_name": "نام مشتری"},
    },
    ADDITIONAL_DOCUMENT_REQUESTED: {
        "group": GROUP_ORDERS, "recipient": RECIPIENT_CUSTOMER,
        "label": "درخواست مدرک تکمیلی",
        "description": "وقتی شرکت حمل از مشتری مدرک اضافه می‌خواهد؛ لینک بارگذاری ارسال می‌شود.",
        "params": {
            "customer_name": "نام مشتری", "order_id": "شماره سفارش",
            "doc_title": "عنوان مدرک", "link": "لینک بارگذاری",
        },
    },
    ADDITIONAL_DOCUMENT_UPLOADED: {
        "group": GROUP_ORDERS, "recipient": RECIPIENT_COMPANY,
        "label": "بارگذاری مدرک تکمیلی",
        "description": "وقتی مشتری مدرک تکمیلی درخواستی را بارگذاری می‌کند.",
        "params": {
            "company_name": "نام شرکت حمل", "order_id": "شماره سفارش",
            "doc_title": "عنوان مدرک", "customer_name": "نام مشتری",
        },
    },

    COMPANY_REGISTRATION_RECEIVED: {
        "group": GROUP_COMPANY, "recipient": RECIPIENT_COMPANY,
        "label": "دریافت اطلاعات و مدارک ثبت‌نام",
        "description": "وقتی شرکت حمل اطلاعات و مدارک ثبت‌نام را ارسال (یا دوباره ارسال) می‌کند.",
        "params": {"contact_name": "نام نماینده‌ی شرکت", "company_name": "نام شرکت"},
    },
    COMPANY_VERIFIED: {
        "group": GROUP_COMPANY, "recipient": RECIPIENT_COMPANY,
        "label": "تایید و فعال‌سازی شرکت",
        "description": "وقتی ثبت‌نام شرکت تایید و پنل آن فعال می‌شود.",
        "params": {"contact_name": "نام نماینده‌ی شرکت", "company_name": "نام شرکت"},
    },
    COMPANY_REJECTED: {
        "group": GROUP_COMPANY, "recipient": RECIPIENT_COMPANY,
        "label": "نیاز به اصلاح مدارک شرکت",
        "description": "وقتی کارشناس ثبت‌نام شرکت را رد می‌کند و اصلاح مدارک لازم است.",
        "params": {"contact_name": "نام نماینده‌ی شرکت", "company_name": "نام شرکت", "reason": "دلیل"},
    },
    FORWARDER_STAFF_CREATED: {
        "group": GROUP_COMPANY, "recipient": RECIPIENT_USER,
        "label": "ایجاد حساب کارمند شرکت حمل",
        "description": "وقتی برای یک کارمند شرکت حمل حساب کاربری ساخته می‌شود.",
        "params": {"staff_name": "نام کارمند", "company_name": "نام شرکت", "mobile": "شماره موبایل (نام کاربری)"},
    },

    LAND_REQUEST_CREATED_CUSTOMER: {
        "group": GROUP_LAND, "recipient": RECIPIENT_CUSTOMER,
        "label": "ثبت درخواست حمل زمینی",
        "description": "پس از ثبت درخواست و ارسال آن برای شرکت‌های واجد شرایط.",
        "params": {"customer_name": "نام مشتری", "request_ref": "کد درخواست", "carriers_count": "تعداد شرکت‌های مطلع‌شده"},
    },
    LAND_REQUEST_NEW_FORWARDER: {
        "group": GROUP_LAND, "recipient": RECIPIENT_COMPANY,
        "label": "درخواست حمل زمینی جدید (به شرکت حمل)",
        "description": "برای هر شرکت واجد شرایط، هنگام ثبت یا انتشار دوباره‌ی درخواست.",
        "params": {
            "company_name": "نام شرکت حمل", "request_ref": "کد درخواست",
            "scope": "نوع حمل (درون‌شهری/برون‌شهری/بین‌المللی)", "origin": "مبدا", "destination": "مقصد",
            "vehicle": "نوع ناوگان", "price": "کرایه‌ی پیشنهادی (ریال)", "pickup_date": "تاریخ بارگیری",
        },
    },
    LAND_REQUEST_ACCEPTED_CUSTOMER: {
        "group": GROUP_LAND, "recipient": RECIPIENT_CUSTOMER,
        "label": "پذیرش درخواست حمل زمینی (به مشتری)",
        "description": "وقتی اولین شرکت حمل درخواست را می‌پذیرد.",
        "params": {
            "customer_name": "نام مشتری", "request_ref": "کد درخواست",
            "company_name": "نام شرکت حمل", "company_phone": "تلفن شرکت حمل",
        },
    },
    LAND_REQUEST_STATUS_CUSTOMER: {
        "group": GROUP_LAND, "recipient": RECIPIENT_CUSTOMER,
        "label": "به‌روزرسانی وضعیت بار زمینی",
        "description": "وقتی شرکت حمل وضعیت را به «در حال حمل» یا «تحویل شده» تغییر می‌دهد.",
        "params": {
            "customer_name": "نام مشتری", "request_ref": "کد درخواست",
            "status": "وضعیت جدید", "company_name": "نام شرکت حمل",
        },
    },
    LAND_REQUEST_CANCELLED_FORWARDER: {
        "group": GROUP_LAND, "recipient": RECIPIENT_COMPANY,
        "label": "لغو درخواست پذیرفته‌شده (به شرکت حمل)",
        "description": "وقتی مشتری درخواستی را که شرکت پذیرفته بود لغو می‌کند.",
        "params": {"company_name": "نام شرکت حمل", "request_ref": "کد درخواست", "reason": "دلیل لغو"},
    },
    LAND_REQUEST_EXPIRED_CUSTOMER: {
        "group": GROUP_LAND, "recipient": RECIPIENT_CUSTOMER,
        "label": "پایان مهلت درخواست حمل زمینی",
        "description": "وقتی هیچ شرکتی در مهلت تعیین‌شده درخواست را نمی‌پذیرد.",
        "params": {"customer_name": "نام مشتری", "request_ref": "کد درخواست"},
    },
    LAND_DOCUMENT_REVIEWED: {
        "group": GROUP_LAND, "recipient": RECIPIENT_CUSTOMER,
        "label": "بررسی مدرک بار زمینی",
        "description": "وقتی شرکت حمل مدرک بارگذاری‌شده‌ی درخواست زمینی را تایید یا رد می‌کند.",
        "params": {
            "customer_name": "نام مشتری", "request_ref": "کد درخواست", "doc_title": "عنوان مدرک",
            "result": "نتیجه (تایید شد/رد شد)", "reason": "توضیح",
        },
    },

    TICKET_ANSWERED: {
        "group": GROUP_SUPPORT, "recipient": RECIPIENT_USER,
        "label": "پاسخ به تیکت پشتیبانی",
        "description": "وقتی کارشناس پشتیبانی به تیکت کاربر پاسخ می‌دهد.",
        "params": {"user_name": "نام کاربر", "ticket_id": "شماره تیکت", "subject": "موضوع تیکت"},
    },
}


# متن پیش‌فرض هر رویداد (مهاجرت داده‌ای core/0007 با همین‌ها رویدادها را
# می‌سازد و داشبورد با آن‌ها «بازگردانی متن پیش‌فرض» را انجام می‌دهد).
DEFAULT_TEXTS = {
    OTP_VERIFICATION: "کد تایید باریار: {code}\nلطفاً این کد را در اختیار هیچ‌کس قرار ندهید.",
    CUSTOMER_WELCOME: (
        "{customer_name} عزیز، به خانواده‌ی باریار خوش آمدید! از این پس استعلام و ثبت حمل هوایی، "
        "دریایی و زمینی فقط چند کلیک با شما فاصله دارد."
    ),
    ORDER_DRAFT_CREATED: (
        "{customer_name} عزیز، سفارش {order_id} از {origin} به {destination} به‌صورت پیش‌نویس ثبت شد. "
        "برای نهایی‌شدن، اطلاعات و مدارک را در پنل باریار تکمیل کنید."
    ),
    RATE_MATCH_FOUND_CUSTOMER: (
        "{customer_name} عزیز، سفارش {order_id} شما به «{forwarder_name}» سپرده شد؛ "
        "کارشناسان این شرکت به‌زودی پیگیری را آغاز می‌کنند."
    ),
    RATE_MATCH_FOUND_FORWARDER: (
        "همکار گرامی {company_name}، سفارش تازه‌ی {order_id} ({origin} به {destination}) "
        "از {customer_name} بر اساس نرخ شما ثبت شد. جزئیات در پنل باریار."
    ),
    ORDER_FINALIZED: (
        "{customer_name} عزیز، سفارش {order_id} با مبلغ {final_price} ریال نهایی و برای «{forwarder_name}» "
        "ارسال شد. سفر بار شما از همین حالا آغاز می‌شود!"
    ),
    ORDER_STATUS_CHANGED: "{customer_name} عزیز، وضعیت سفارش {order_id} به «{status}» تغییر کرد. ({forwarder_name})",
    ORDER_DOCUMENT_REVIEWED: "{customer_name} عزیز، مدرک «{doc_title}» سفارش {order_id} {result}. توضیح: {reason}",
    ORDER_MESSAGE_TO_CUSTOMER: (
        "{customer_name} عزیز، «{forwarder_name}» درباره‌ی سفارش {order_id} پیام تازه‌ای برایتان فرستاد. "
        "پاسخ در پنل باریار."
    ),
    ORDER_MESSAGE_TO_FORWARDER: "همکار گرامی {company_name}، {customer_name} درباره‌ی سفارش {order_id} پیام جدیدی ارسال کرد.",
    ADDITIONAL_DOCUMENT_REQUESTED: (
        "{customer_name} عزیز، برای ادامه‌ی سفارش {order_id} به مدرک «{doc_title}» نیاز داریم. "
        "بارگذاری از این لینک: {link}"
    ),
    ADDITIONAL_DOCUMENT_UPLOADED: "همکار گرامی {company_name}، {customer_name} مدرک «{doc_title}» سفارش {order_id} را بارگذاری کرد.",
    COMPANY_REGISTRATION_RECEIVED: (
        "{contact_name} گرامی، اطلاعات و مدارک «{company_name}» در باریار دریافت شد "
        "و حداکثر ظرف دو روز کاری بررسی می‌شود."
    ),
    COMPANY_VERIFIED: (
        "تبریک {contact_name} گرامی! حساب «{company_name}» در باریار تایید و فعال شد. "
        "از همین حالا می‌توانید درخواست‌ها را دریافت کنید."
    ),
    COMPANY_REJECTED: (
        "{contact_name} گرامی، مدارک «{company_name}» نیاز به اصلاح دارد: {reason}. "
        "لطفاً از پنل باریار اصلاح و دوباره ارسال کنید."
    ),
    FORWARDER_STAFF_CREATED: (
        "{staff_name} عزیز، حساب کاربری شما در «{company_name}» روی باریار ساخته شد. ورود با شماره {mobile}؛ "
        "رمز موقت، کد ملی شماست و در اولین ورود باید تغییر کند."
    ),
    LAND_REQUEST_CREATED_CUSTOMER: (
        "{customer_name} عزیز، درخواست حمل {request_ref} ثبت و برای {carriers_count} شرکت حمل ارسال شد. "
        "به محض پذیرش خبرتان می‌کنیم."
    ),
    LAND_REQUEST_NEW_FORWARDER: (
        "بار تازه برای {company_name}! {request_ref} ({scope}): {origin} به {destination}، {vehicle}، "
        "بارگیری {pickup_date}، کرایه {price} ریال. اولین پذیرنده برنده است!"
    ),
    LAND_REQUEST_ACCEPTED_CUSTOMER: (
        "{customer_name} عزیز، خبر خوب! «{company_name}» درخواست حمل {request_ref} را پذیرفت. "
        "تماس با شرکت: {company_phone}"
    ),
    LAND_REQUEST_STATUS_CUSTOMER: "{customer_name} عزیز، وضعیت بار {request_ref} اکنون «{status}» است. ({company_name})",
    LAND_REQUEST_CANCELLED_FORWARDER: "همکار گرامی {company_name}، درخواست {request_ref} توسط مشتری لغو شد. دلیل: {reason}",
    LAND_REQUEST_EXPIRED_CUSTOMER: (
        "{customer_name} عزیز، مهلت پذیرش درخواست {request_ref} تمام شد. با کرایه‌ی جدید دوباره "
        "منتشرش کنید تا شرکت‌های بیشتری ببینند."
    ),
    LAND_DOCUMENT_REVIEWED: "{customer_name} عزیز، مدرک «{doc_title}» درخواست {request_ref} {result}. توضیح: {reason}",
    TICKET_ANSWERED: "{user_name} عزیز، به تیکت شماره {ticket_id} («{subject}») پاسخ داده شد. پاسخ را در پنل باریار ببینید.",
}

GROUP_ORDER = [GROUP_ACCOUNT, GROUP_ORDERS, GROUP_COMPANY, GROUP_LAND, GROUP_SUPPORT]


# مقادیر نمونه برای پیش‌نمایش متن در داشبورد
SAMPLE_VALUES = {
    "code": "48213", "customer_name": "مریم احمدی", "order_id": "1024", "origin": "تهران",
    "destination": "دبی", "forwarder_name": "ترابر آسیا", "company_name": "ترابر آسیا",
    "final_price": "125,000,000", "status": "تایید شده", "doc_title": "فاکتور تجاری",
    "result": "تایید شد", "reason": "-", "link": "https://example.com/u/abc",
    "contact_name": "علی رضایی", "staff_name": "سارا کریمی", "mobile": "09121234567",
    "request_ref": "LF-000128", "carriers_count": "7", "scope": "برون‌شهری (داخل ایران)",
    "vehicle": "نیسان (وانت آبی)", "price": "45,000,000", "pickup_date": "1405/07/12",
    "company_phone": "021-88776655", "user_name": "مریم احمدی", "ticket_id": "352",
    "subject": "پیگیری سفارش",
}


def get_event_params(code):
    return NOTIFICATION_EVENTS.get(code, {}).get("params", {})


def render_sample(text, code):
    """متن را با مقادیر نمونه‌ی متغیرهای همان رویداد جایگذاری می‌کند."""
    params = get_event_params(code)
    values = {key: SAMPLE_VALUES.get(key, f"[{label}]") for key, label in params.items()}
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        return text
