from django.db import migrations


def seed(apps, schema_editor):
    SmsEvent = apps.get_model("core", "SmsEvent")
    events = [
        dict(
            code="land_request_new_forwarder",
            label="درخواست حمل زمینی جدید (به شرکت حمل)",
            description="وقتی مشتری درخواست حمل زمینی ثبت می‌کند، برای هر شرکت واجد شرایط ارسال می‌شود.",
            is_enabled=False,
            send_mode="custom",
            custom_text=(
                "درخواست حمل زمینی جدید {request_ref} ({scope}): {origin} به {destination}، "
                "{vehicle}، بارگیری {pickup_date}، کرایه‌ی پیشنهادی {price} ریال. "
                "برای پذیرش به پنل مراجعه کنید."
            ),
        ),
        dict(
            code="land_request_accepted_customer",
            label="پذیرش درخواست حمل زمینی (به مشتری)",
            description="وقتی اولین شرکت حمل درخواست زمینی مشتری را می‌پذیرد.",
            is_enabled=False,
            send_mode="custom",
            custom_text=(
                "درخواست حمل {request_ref} شما توسط «{company_name}» پذیرفته شد. "
                "تلفن شرکت: {company_phone}"
            ),
        ),
    ]
    for event in events:
        SmsEvent.objects.get_or_create(code=event["code"], defaults=event)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_alter_smsevent_parameter_mapping_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
