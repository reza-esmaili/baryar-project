# ════════════════════════════════════════════════════════════════
# این validator مرکزی است و در همه جا (پروفایل، سفارش، فرم‌ها)
# استفاده می‌شود تا صحت کد ملی ایرانی بررسی شود.
# ════════════════════════════════════════════════════════════════

import re
from django.core.exceptions import ValidationError
 
 
def validate_iranian_national_code(value):
    """
    اعتبارسنجی کد ملی ایرانی با الگوریتم چک‌دیجیت.
 
    قوانین:
    - دقیقاً ۱۰ رقم
    - ارقام همه یکسان نباشند (مثل 0000000000)
    - رقم کنترل با الگوریتم استاندارد مطابقت داشته باشد
    """
    if value in (None, ""):
        return  # اگر فیلد اختیاری است، خالی بودن مجاز است
 
    code = str(value).strip()
 
    # فقط رقم و دقیقاً ۱۰ تا
    if not re.match(r"^\d{10}$", code):
        raise ValidationError("کد ملی باید دقیقاً ۱۰ رقم باشد.")
 
    # ارقام تکراری (مثل 1111111111) نامعتبرند
    if code == code[0] * 10:
        raise ValidationError("کد ملی وارد شده معتبر نیست.")
 
    # الگوریتم چک‌دیجیت
    check = int(code[9])
    s = sum(int(code[i]) * (10 - i) for i in range(9))
    remainder = s % 11
 
    if remainder < 2:
        valid = (check == remainder)
    else:
        valid = (check == 11 - remainder)
 
    if not valid:
        raise ValidationError("کد ملی وارد شده معتبر نیست.")