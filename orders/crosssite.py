# ════════════════════════════════════════════════════════════════
# فایل: baryar/orders/crosssite.py  (فایل جدید بساز)
#
# این فایل مدیریت توکن‌های یکبار مصرف برای انتقال امن
# سفارش از سایت بازرگانی (Tejarat) به Baryar را انجام می‌دهد.
# ════════════════════════════════════════════════════════════════
import hashlib
import hmac
import json
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


# ── تنظیمات ──────────────────────────────────────────────────────
TOKEN_TTL_SECONDS = 5 * 60   # ۵ دقیقه
CACHE_PREFIX      = "crosssite_order_token:"


def _sign(payload_str: str) -> str:
    """امضای HMAC-SHA256 با SECRET_KEY پروژه"""
    secret = settings.SECRET_KEY.encode()
    return hmac.new(secret, payload_str.encode(), hashlib.sha256).hexdigest()


def create_order_token(order_data: dict) -> str:
    """
    یک token یکبار مصرف امن می‌سازد.

    order_data باید شامل باشد:
    {
        "rate_id":            int,
        "origin_city":        int,
        "destination_port":   int,
        "transport_mode":     str,
        "cargo_type":         int,
        "shipping_procedure": str,
        "actual_weight":      float | None,
        "dimensions":         list,
        "container_size":     str | None,
        "container_type":     str | None,
        "container_count":    int | None,
        "needs_office_packaging":   bool,
        "needs_onsite_packaging":   bool,
        "needs_doorstep_packaging": bool,
    }

    برمی‌گرداند: یک token string که کاربر می‌تواند در URL ببرد.
    """
    raw_token = secrets.token_urlsafe(32)  # 256 بیت تصادفی

    payload_str = json.dumps(order_data, ensure_ascii=False, sort_keys=True)
    signature   = _sign(payload_str)

    cache_value = {
        "payload":   order_data,
        "signature": signature,
        "used":      False,
        "created_at": timezone.now().isoformat(),
    }

    cache_key = f"{CACHE_PREFIX}{raw_token}"
    cache.set(cache_key, json.dumps(cache_value), timeout=TOKEN_TTL_SECONDS)

    return raw_token


def consume_order_token(token: str) -> dict | None:
    """
    توکن را verify و مصرف می‌کند.

    اگر valid بود → dict اطلاعات سفارش برمی‌گرداند و توکن را حذف می‌کند.
    اگر invalid/expired/used بود → None برمی‌گرداند.

    یکبار مصرف: بعد از اولین استفاده موفق، از cache حذف می‌شود.
    """
    if not token or len(token) > 128:
        return None

    cache_key = f"{CACHE_PREFIX}{token}"
    raw = cache.get(cache_key)

    if not raw:
        # منقضی شده یا وجود ندارد
        return None

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if data.get("used"):
        # قبلاً استفاده شده
        return None

    # verify امضا
    payload     = data.get("payload", {})
    payload_str = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    expected_sig = _sign(payload_str)

    if not hmac.compare_digest(expected_sig, data.get("signature", "")):
        # دستکاری شده
        cache.delete(cache_key)
        return None

    # توکن معتبر است — آن را حذف کن (یکبار مصرف)
    cache.delete(cache_key)

    return payload