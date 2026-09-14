import os

from django.db import migrations


def seed_data(apps, schema_editor):
    SmsProviderConfig = apps.get_model("core", "SmsProviderConfig")
    SmsEvent = apps.get_model("core", "SmsEvent")

    SmsProviderConfig.objects.get_or_create(
        provider_type="smsir",
        defaults={
            "api_key": os.environ.get("SMSIR_API_KEY", ""),
            "default_line_number": "",
            "is_active": True,
        },
    )

    events = [
        dict(
            code="otp_verification",
            label="ارسال کد تایید (OTP)",
            description="هنگام ورود، ثبت‌نام یا فراموشی رمز عبور برای تایید شماره موبایل ارسال می‌شود.",
            is_enabled=True,
            send_mode="template",
            template_id=438020,
            parameter_mapping={"code": "OTP"},
        ),
        dict(
            code="order_draft_created",
            label="ثبت پیش‌نویس سفارش",
            description="وقتی مشتری نرخ را انتخاب می‌کند و درخواست به‌عنوان پیش‌نویس ثبت می‌شود.",
            is_enabled=False,
            send_mode="custom",
            custom_text="مشتری گرامی، درخواست شما با شماره {order_id} از {origin} به {destination} به‌عنوان پیش‌نویس ثبت شد.",
        ),
        dict(
            code="rate_match_found_customer",
            label="پیدا شدن تطبیق نرخ (به مشتری)",
            description="همزمان با ثبت پیش‌نویس، به مشتری اطلاع می‌دهد نرخش با کدام فورواردر تطبیق یافت.",
            is_enabled=False,
            send_mode="custom",
            custom_text="سفارش {order_id} شما با فورواردر «{forwarder_name}» تطبیق یافت.",
        ),
        dict(
            code="rate_match_found_forwarder",
            label="پیدا شدن تطبیق نرخ (به فورواردر)",
            description="به فورواردر/شعبه صاحب نرخ اطلاع می‌دهد یک درخواست جدید مطابق نرخش ثبت شده است.",
            is_enabled=False,
            send_mode="custom",
            custom_text="یک درخواست جدید (سفارش {order_id}) از {origin} به {destination} برای مشتری {customer_name} مطابق نرخ شما ثبت شد.",
        ),
        dict(
            code="order_finalized",
            label="تکمیل نهایی سفارش (ایجاد بار)",
            description="وقتی مشتری اطلاعات و مدارک سفارش را کامل می‌کند و سفارش برای بررسی فورواردر ارسال می‌شود.",
            is_enabled=False,
            send_mode="custom",
            custom_text="سفارش {order_id} شما با مبلغ نهایی {final_price} ریال ثبت نهایی شد.",
        ),
        dict(
            code="additional_document_requested",
            label="درخواست مدرک تکمیلی دریافت شد",
            description="وقتی فورواردر از مشتری درخواست مدرک اضافه می‌کند، لینک آپلود برای مشتری پیامک می‌شود.",
            is_enabled=False,
            send_mode="custom",
            custom_text="مشتری گرامی، برای سفارش {order_id} به مدرک «{doc_title}» نیاز است. لینک آپلود: {link}",
        ),
    ]

    for event in events:
        SmsEvent.objects.get_or_create(code=event["code"], defaults=event)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_smsevent_smsproviderconfig"),
    ]

    operations = [
        migrations.RunPython(seed_data, noop_reverse),
    ]
