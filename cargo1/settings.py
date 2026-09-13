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
SMS_PROVIDER = "smsir"
SMSIR_API_KEY = os.environ.get('SMSIR_API_KEY', '')
SMSIR_VERIFY_BASE_URL = "https://api.sms.ir/v1/send/verify"

SMS_TEMPLATES = {
    "otp": {
        "template_id": 438020,
        "parameters": {
            "code": "OTP",
        },
    },
    # قالب پیامک درخواست مدرک تکمیلی از مشتری
    # template_id را پس از ساخت قالب در پنل sms.ir وارد کنید
    # متغیرهای قالب: OrderId (شماره سفارش)، DocTitle (عنوان مدرک)، Link (لینک آپلود)
    "doc_request_link": {
        "template_id": 0,   # ← شناسه قالب sms.ir را اینجا وارد کنید
        "parameters": {
            "order_id":  "OrderId",
            "doc_title": "DocTitle",
            "link":      "Link",
        },
    },
}

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