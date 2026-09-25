from django.db import migrations


def mark_existing_companies_air(apps, schema_editor):
    # تا پیش از این مهاجرت فقط حمل هوایی وجود داشت؛ شرکت‌های موجود همین دسته
    # را داشته‌اند. دسته‌های جدید را ادمین یا خود شرکت فعال می‌کند.
    ForwarderCompany = apps.get_model("forwarders", "ForwarderCompany")
    ForwarderCompany.objects.update(service_air=True)


class Migration(migrations.Migration):

    dependencies = [
        ("forwarders", "0005_forwardercompany_service_air_and_more"),
    ]

    operations = [
        migrations.RunPython(mark_existing_companies_air, migrations.RunPython.noop),
    ]
