from django.db import migrations

# متن پیش‌فرض هر رویداد در core/services/notifications/events.py (DEFAULT_TEXTS)
# تعریف شده تا دکمه‌ی «بازگردانی متن پیش‌فرض» داشبورد هم از همان استفاده کند.
# رویدادهای تازه غیرفعال ساخته می‌شوند تا بدون تصمیم مدیر، اعتبار پیامکی مصرف نشود.

# متن‌های پیش‌فرض قبلی؛ اگر مدیر تغییرشان نداده باشد با نسخه‌ی جدید جایگزین می‌شوند.
PREVIOUS_DEFAULTS = {
    "order_draft_created": "مشتری گرامی، درخواست شما با شماره {order_id} از {origin} به {destination} به‌عنوان پیش‌نویس ثبت شد.",
    "rate_match_found_customer": "سفارش {order_id} شما با فورواردر «{forwarder_name}» تطبیق یافت.",
    "rate_match_found_forwarder": "یک درخواست جدید (سفارش {order_id}) از {origin} به {destination} برای مشتری {customer_name} مطابق نرخ شما ثبت شد.",
    "order_finalized": "سفارش {order_id} شما با مبلغ نهایی {final_price} ریال ثبت نهایی شد.",
    "additional_document_requested": "مشتری گرامی، برای سفارش {order_id} به مدرک «{doc_title}» نیاز است. لینک آپلود: {link}",
    "land_request_new_forwarder": (
        "درخواست حمل زمینی جدید {request_ref} ({scope}): {origin} به {destination}، "
        "{vehicle}، بارگیری {pickup_date}، کرایه‌ی پیشنهادی {price} ریال. "
        "برای پذیرش به پنل مراجعه کنید."
    ),
    "land_request_accepted_customer": (
        "درخواست حمل {request_ref} شما توسط «{company_name}» پذیرفته شد. "
        "تلفن شرکت: {company_phone}"
    ),
}


def seed(apps, schema_editor):
    from core.services.notifications.events import DEFAULT_TEXTS, NOTIFICATION_EVENTS

    SmsEvent = apps.get_model("core", "SmsEvent")
    for code, meta in NOTIFICATION_EVENTS.items():
        text = DEFAULT_TEXTS.get(code, "")
        event, created = SmsEvent.objects.get_or_create(
            code=code,
            defaults={
                "label": meta["label"],
                "description": meta["description"],
                "is_enabled": False,
                "send_mode": "custom",
                "custom_text": text,
            },
        )
        if created:
            continue

        fields = []
        if event.label != meta["label"] or event.description != meta["description"]:
            event.label, event.description = meta["label"], meta["description"]
            fields += ["label", "description"]
        untouched = not event.custom_text or event.custom_text == PREVIOUS_DEFAULTS.get(code)
        if text and untouched and event.custom_text != text:
            event.custom_text = text
            fields.append("custom_text")
        if fields:
            event.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_alter_smsproviderconfig_options_and_more"),
        ("core", "0005_seed_land_freight_sms_events"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
