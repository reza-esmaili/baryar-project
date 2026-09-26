from django.db import migrations

# (کد، عنوان، توضیح)
DOCUMENT_TYPES = [
    ("company-articles-of-association", "اساسنامه‌ی شرکت", "آخرین اساسنامه‌ی ثبت‌شده‌ی شرکت"),
    ("company-establishment-notice", "آگهی تاسیس (روزنامه‌ی رسمی)", "آگهی تاسیس منتشرشده در روزنامه‌ی رسمی"),
    ("company-latest-changes", "آخرین تغییرات روزنامه‌ی رسمی", "آخرین آگهی تغییرات (مدیران، آدرس، سرمایه)"),
    ("company-ceo-national-card", "کارت ملی مدیرعامل", "تصویر پشت و روی کارت ملی"),
    ("license-air-freight", "مجوز فعالیت حمل هوایی", "گواهی عضویت IATA یا قرارداد نمایندگی با شرکت هواپیمایی"),
    ("license-sea-freight", "مجوز فعالیت حمل دریایی", "پروانه‌ی فعالیت از سازمان بنادر و دریانوردی"),
    ("license-land-intracity", "مجوز حمل بار درون‌شهری", "مجوز شهرداری یا پروانه‌ی اتحادیه‌ی باربری‌ها"),
    ("license-road-transport", "پروانه‌ی فعالیت حمل‌ونقل جاده‌ای", "پروانه‌ی شرکت حمل‌ونقل از سازمان راهداری و حمل‌ونقل جاده‌ای"),
    ("license-international-road", "پروانه‌ی حمل‌ونقل بین‌المللی جاده‌ای", "پروانه‌ی بین‌المللی و مدارک کارنه‌ی تیر (TIR)"),
    ("carrier-liability-insurance", "بیمه‌نامه‌ی مسئولیت متصدی حمل", "بیمه‌نامه‌ی معتبر مسئولیت حمل کالا"),
]

# (کد مدرک، دسته، اجباری، ترتیب)
REQUIREMENTS = [
    ("company-articles-of-association", "all", True, 1),
    ("company-establishment-notice", "all", True, 2),
    ("company-latest-changes", "all", True, 3),
    ("company-ceo-national-card", "all", True, 4),
    ("license-air-freight", "air", False, 10),
    ("license-sea-freight", "sea", True, 20),
    ("license-land-intracity", "land_intracity", True, 30),
    ("license-road-transport", "land_domestic", True, 40),
    ("license-road-transport", "land_international", True, 41),
    ("license-international-road", "land_international", True, 50),
    ("carrier-liability-insurance", "land_domestic", False, 60),
    ("carrier-liability-insurance", "land_international", False, 61),
]

# مدارک ثابت قبلی (فیلد doc_type) ← نوع مدرک قابل تعریف
LEGACY_COMPANY_DOC_TYPES = {
    "articles_of_association": "company-articles-of-association",
    "establishment_notice": "company-establishment-notice",
    "latest_changes": "company-latest-changes",
    "ceo_national_card": "company-ceo-national-card",
}


def seed(apps, schema_editor):
    DocumentType = apps.get_model("documents", "DocumentType")
    Requirement = apps.get_model("forwarders", "CompanyDocumentRequirement")
    IdentityDocument = apps.get_model("accounts", "IdentityDocument")

    types = {}
    for code, title, description in DOCUMENT_TYPES:
        types[code], _ = DocumentType.objects.get_or_create(
            code=code, defaults={"title": title, "description": description},
        )

    for code, service, required, order in REQUIREMENTS:
        Requirement.objects.get_or_create(
            document_type=types[code], service=service,
            defaults={"is_required": required, "sort_order": order},
        )

    for legacy, code in LEGACY_COMPANY_DOC_TYPES.items():
        IdentityDocument.objects.filter(
            company__isnull=False, doc_type=legacy, document_type__isnull=True,
        ).update(document_type=types[code])


class Migration(migrations.Migration):

    dependencies = [
        ("forwarders", "0007_companydocumentrequirement"),
        ("accounts", "0014_identitydocument_document_type_and_more"),
        ("documents", "0006_documentrule_land_scope"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
