def display_name(user):
    """نام قابل‌نمایش کاربر برای متن پیامک/اعلان؛ اگر نام ثبت نشده، شماره موبایل."""
    if user is None:
        return ""
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full_name or getattr(user, "mobile", "") or ""
