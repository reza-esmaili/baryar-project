"""
Django settings for cargo1 project.
"""

from pathlib import Path
import os
from datetime import timedelta

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
# مقدار واقعی از فایل .env (که کامیت نمی‌شود) خوانده می‌شود؛ مقدار پیش‌فرض
# فقط یک نگهبان ایمنی برای زمانی است که .env به هر دلیلی موجود نباشد.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-fallback-key-set-DJANGO_SECRET_KEY-in-env',
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if h.strip()
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'forwarders',
    'locations',
    'rates',
    'core',
    'customer',
    'orders',
    'django.contrib.humanize',
    'rest_framework',
    'django_filters',
    'support',
    'django_jalali',
    'documents',
    'django_extensions',
    'corsheaders',
    'panel',
    'admin_dashboard',
]

ASGI_APPLICATION = "cargo1.asgi.application"

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cargo1.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'panel.context_processors.forwarder_permissions',
            ],
        },
    },
]

WSGI_APPLICATION = 'cargo1.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Tehran'
USE_TZ = False

# Static files
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# Media (uploaded) files — باید در پوشه اختصاصی media/ باشند، نه ریشه پروژه؛
# در غیر این صورت وقتی DEBUG=True است، هر فایلی در ریشه پروژه (از جمله
# settings.py و db.sqlite3) از طریق آدرس‌دهی مستقیم قابل دانلود می‌شود.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# فضای ذخیره‌سازی مدارک حساس (هویتی/سفارش) — عمداً خارج از MEDIA_ROOT است تا
# هرگز زیر آدرس عمومی /media/ سرو نشود؛ دسترسی فقط از طریق ویوهای محافظت‌شده
# در documents/views.py ممکن است (نگاه کنید به core/storage.py).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "protected": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {
            "location": BASE_DIR / "protected_media",
            "base_url": None,
        },
    },
}

# --- کش ---
# اگر REDIS_URL در .env تنظیم شده باشد (برای production)، از Redis استفاده
# می‌شود؛ در غیر این صورت (مثل این محیط توسعه که Redis روی آن نصب نیست) به
# LocMemCache برمی‌گردد — کش واقعی و کاربردی برای یک فرآیند، فقط بین چند
# worker/سرور مشترک نیست. سوییچ به Redis در آینده فقط با تنظیم REDIS_URL
# ممکن است، بدون نیاز به تغییر کد.
REDIS_URL = os.environ.get('REDIS_URL', '')
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# --- صف پردازش ناهمزمان (Celery) ---
# اگر CELERY_BROKER_URL تنظیم نشده باشد (مثل این محیط توسعه که broker واقعی
# روی آن اجرا نیست)، Celery در حالت eager اجرا می‌شود: هر task بلافاصله و
# همزمان در همان پردازش فراخوانی‌کننده اجرا می‌شود، دقیقاً مثل یک فراخوانی
# تابع معمولی، بدون نیاز به worker یا broker جداگانه. سوییچ به اجرای واقعی
# ناهمزمان در آینده فقط با تنظیم CELERY_BROKER_URL ممکن است، بدون تغییر کد.
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', '')
CELERY_TASK_ALWAYS_EAGER = not CELERY_BROKER_URL
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_RESULT_BACKEND = CELERY_BROKER_URL or None
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = 'customer:login'

# --- تنظیمات امنیتی که فقط در production (DEBUG=False) فعال می‌شوند ---
# در DEBUG=True فعال نمی‌شوند چون کوکی/HTTPS اجباری، توسعه محلی روی HTTP
# ساده را می‌شکند.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000  # ۱ سال
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Cargo Platform API',
    'DESCRIPTION': 'API برای پلتفرم حمل و نقل بین‌المللی',
    'VERSION': '1.0.0',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}

# --- SMS Configuration ---
# تنظیمات اتصال به سامانه پیامکی (کلید API، شماره خط) و متن/قالب هر رویداد
# دیگر اینجا نیست — از پایگاه‌داده خوانده می‌شود و از داشبورد ادمین
# (/staff/settings/sms/) قابل تغییر است. به core.models.SmsProviderConfig
# و core.models.SmsEvent مراجعه کنید.

OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_EXPIRE_SECONDS = 120  # ۲ دقیقه فرصت برای وارد کردن کد


CORS_ALLOWED_ORIGINS = [
    "http://localhost:8001",           # سایت بازرگانی در development
    "https://trading.yourdomain.com",  # سایت بازرگانی در production
]

# فقط GET و POST مجاز باشند
CORS_ALLOW_METHODS = ["GET", "POST", "OPTIONS"]

CORS_ALLOW_METHODS = [
    "GET",
    "POST",
    "OPTIONS",
]