# راه‌اندازی باریار روی یک سیستم جدید

گیت فقط **کد** را منتقل می‌کند. دیتابیس (`db.sqlite3`)، فایل‌های آپلودشده (`media/`، `protected_media/`)،
فایل `.env` و فایل‌های فونت ایران‌سنس عمداً در گیت نیستند و باید جدا منتقل یا ساخته شوند.

## ۱. پیش‌نیازها

- Python نسخه‌ی **3.12 یا بالاتر** (Django 6 با نسخه‌های قدیمی‌تر نصب نمی‌شود)
- Git
- برای ساخت PDF فاکتور (WeasyPrint):
  - ویندوز: نصب GTK/Pango طبق [راهنمای WeasyPrint برای ویندوز](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows)
  - لینوکس (Debian/Ubuntu): `sudo apt install libpango-1.0-0 libpangoft2-1.0-0`

## ۲. دریافت کد و نصب وابستگی‌ها

```bash
git clone https://github.com/reza-esmaili/baryar-project.git
cd baryar-project

python -m venv .venv
# ویندوز (PowerShell):
.venv\Scripts\activate
# لینوکس/مک:
source .venv/bin/activate

pip install -r requirements.txt
```

## ۳. فایل تنظیمات `.env`

```bash
# ویندوز: copy .env.example .env      لینوکس/مک: cp .env.example .env
```

سپس در `.env`:

- `DJANGO_SECRET_KEY`: یک کلید تازه بسازید:
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `DJANGO_DEBUG=True` برای اجرای محلی. **بدون این، `runserver` فایل‌های CSS/JS را سرو نمی‌کند و ظاهر سایت به‌هم می‌ریزد.**
  روی سرور واقعی `False` بگذارید و فایل‌های استاتیک را با وب‌سرور سرو کنید.
- `DJANGO_ALLOWED_HOSTS`: مثلاً `127.0.0.1,localhost` یا دامنه‌ی سرور.

## ۴. دیتابیس — یکی از دو راه

**الف) همان داده‌های سیستم فعلی (کاربران، شرکت‌ها، نرخ‌ها، سفارش‌ها و ...)**
از سیستم قبلی این‌ها را در پوشه‌ی پروژه کپی کنید، سپس `migrate` بزنید:

- `db.sqlite3`
- پوشه‌ی `media/` (لوگوها، آواتارها و ...)
- پوشه‌ی `protected_media/` (مدارک هویتی، مدارک سفارش و بار زمینی)

```bash
python manage.py migrate
```

**ب) دیتابیس خالی**

```bash
python manage.py migrate
python manage.py createsuperuser
```

مهاجرت‌ها داده‌های پایه‌ی سامانه را خودشان می‌سازند (رویدادهای پیامکی، انواع مدرک، مدارک ثبت‌نام شرکت‌ها و ...).
کشورها، استان‌ها، شهرها، بنادر و انواع کالا را از «تنظیمات پایه» در داشبورد مدیریت (ایمپورت اکسل) وارد کنید.

## ۵. فونت ایران‌سنس (اختیاری)

فایل‌های نسخه‌ی وب ایران‌سنس (لایسنس‌دار) را در `static/fonts/iransans/` قرار دهید:
`IRANSansWeb_Light.woff2`، `IRANSansWeb.woff2`، `IRANSansWeb_Medium.woff2`، `IRANSansWeb_Bold.woff2`، `IRANSansWeb_Black.woff2`.
بدون آن‌ها، سایت با فونت‌های فعلی (وزیرمتن/بی‌یکان) نمایش داده می‌شود.

## ۶. اجرا

```bash
python manage.py runserver 127.0.0.1:8089
```

- ورود همه‌ی نقش‌ها: http://127.0.0.1:8089/auth/login/
- داشبورد مدیریت: http://127.0.0.1:8089/staff/
- پنل شرکت حمل: http://127.0.0.1:8089/panel/

## ۷. پیامک

تنظیمات سامانه‌ی پیامکی (کلید API، شماره خط) در دیتابیس ذخیره می‌شود، نه در `.env`.
با دیتابیس خالی، از http://127.0.0.1:8089/staff/settings/sms/ سامانه را اضافه و فعال کنید.

## به‌روزرسانی بعدی از گیت

```bash
git pull
pip install -r requirements.txt
python manage.py migrate
```
