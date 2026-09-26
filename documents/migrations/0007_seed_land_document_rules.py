from django.db import migrations

# مدارک پیش‌فرض محموله‌ی حمل زمینی بین‌المللی — مدیر می‌تواند در بخش «قوانین
# مدارک» داشبورد تغییرشان دهد یا برای حوزه‌های دیگر قانون تازه تعریف کند.
DOCUMENTS = [
    # (کد، عنوان، توضیح، اجباری، توضیح برای مشتری)
    ("commercial-invoice", "فاکتور تجاری (Commercial Invoice)", "فاکتور فروش صادراتی/وارداتی کالا", True,
     "فاکتور تجاری با مشخصات فروشنده، خریدار، شرح و ارزش کالا."),
    ("packing-list", "لیست عدل‌بندی (Packing List)", "فهرست بسته‌ها، وزن و ابعاد", True,
     "فهرست بسته‌ها با وزن ناخالص/خالص و ابعاد هر بسته."),
    ("certificate-of-origin", "گواهی مبدا (Certificate of Origin)", "گواهی مبدا صادرشده توسط اتاق بازرگانی", False,
     "در صورت نیاز کشور مقصد به گواهی مبدا، بارگذاری کنید."),
]


def seed(apps, schema_editor):
    DocumentType = apps.get_model("documents", "DocumentType")
    DocumentRule = apps.get_model("documents", "DocumentRule")

    for code, title, description, required, customer_description in DOCUMENTS:
        doc_type, _ = DocumentType.objects.get_or_create(
            code=code, defaults={"title": title, "description": description},
        )
        DocumentRule.objects.get_or_create(
            document_type=doc_type,
            transport_mode="land",
            land_scope="international",
            defaults={
                "title": f"حمل زمینی بین‌المللی — {title}",
                "is_required": required,
                "requirement_level": "transport_mode",
                "customer_description": customer_description,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0006_documentrule_land_scope"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
