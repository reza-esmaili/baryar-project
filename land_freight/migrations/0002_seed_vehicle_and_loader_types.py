from django.db import migrations

VEHICLE_TYPES = [
    ("وانت سبک (پیکان، آریسان)", 700),
    ("نیسان (وانت آبی)", 1500),
    ("کامیونت ۳.۵ تن (ایسوزو، هیوندای)", 3500),
    ("خاور ۵ تن", 5000),
    ("کامیون ۸ تن", 8000),
    ("کامیون تک (۱۰ تا ۱۲ تن)", 12000),
    ("کامیون جفت (۱۸ تن)", 18000),
    ("تریلی (۲۴ تا ۲۵ تن)", 25000),
]

LOADER_TYPES = [
    "مسقف (اتاق‌دار / باکس)",
    "چادری",
    "بغلدار",
    "کفی",
    "یخچال‌دار",
    "کمپرسی",
    "تانکر",
    "کانتینربر",
    "کمرشکن (لوبد)",
    "خودروبر",
]


def seed(apps, schema_editor):
    VehicleType = apps.get_model("land_freight", "VehicleType")
    LoaderType = apps.get_model("land_freight", "LoaderType")
    for name, capacity in VEHICLE_TYPES:
        VehicleType.objects.get_or_create(name=name, defaults={"capacity_kg": capacity})
    for name in LOADER_TYPES:
        LoaderType.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("land_freight", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
