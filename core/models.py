from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SmsProviderConfig(TimeStampedModel):
    """
    تنظیمات اتصال به سامانه پیامکی. فعلاً فقط sms.ir پیاده‌سازی شده، اما
    provider_type برای افزودن سامانه‌های دیگر در آینده گسترش‌پذیر است.
    """

    class ProviderType(models.TextChoices):
        SMSIR = "smsir", "sms.ir"

    provider_type = models.CharField(
        max_length=20, choices=ProviderType.choices, default=ProviderType.SMSIR,
        verbose_name="سامانه پیامکی",
    )
    api_key = models.CharField(max_length=255, blank=True, verbose_name="کلید API")
    default_line_number = models.CharField(
        max_length=20, blank=True, verbose_name="شماره خط پیش‌فرض",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "تنظیمات سامانه پیامکی"
        verbose_name_plural = "تنظیمات سامانه‌های پیامکی"

    def __str__(self):
        return f"{self.get_provider_type_display()} ({'فعال' if self.is_active else 'غیرفعال'})"


class SmsEvent(TimeStampedModel):
    """
    تنظیم متن/قالب پیامک برای یک رویداد مشخص از پلتفرم (ثبت سفارش، تطبیق
    نرخ و ...). مجموعه‌ی رویدادها در کد تعریف می‌شود
    (core/services/notifications/events.py)؛ این مدل فقط پیکربندی هر
    رویداد را نگه می‌دارد و با مهاجرت داده‌ای، یک ردیف برای هر رویداد
    از پیش ساخته می‌شود.
    """

    class SendMode(models.TextChoices):
        CUSTOM = "custom", "متن دلخواه"
        TEMPLATE = "template", "قالب sms.ir"

    code = models.CharField(max_length=64, unique=True, verbose_name="کد رویداد")
    label = models.CharField(max_length=200, verbose_name="عنوان")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    is_enabled = models.BooleanField(default=False, verbose_name="فعال")
    send_mode = models.CharField(
        max_length=10, choices=SendMode.choices, default=SendMode.CUSTOM,
        verbose_name="روش ارسال",
    )
    custom_text = models.TextField(
        blank=True, verbose_name="متن دلخواه",
        help_text="می‌توانید از پارامترهای این رویداد به شکل {نام_پارامتر} استفاده کنید.",
    )
    template_id = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="شناسه قالب sms.ir",
    )
    parameter_mapping = models.JSONField(
        default=dict, blank=True, verbose_name="نگاشت پارامترها",
        help_text="نگاشت نام داخلی هر پارامتر به نام همان پارامتر در قالب sms.ir.",
        encoder=DjangoJSONEncoder,
    )

    class Meta:
        verbose_name = "رویداد پیامکی"
        verbose_name_plural = "رویدادهای پیامکی"
        ordering = ["label"]

    def __str__(self):
        return self.label


class SmsLog(models.Model):
    mobile = models.CharField(max_length=15)
    template_key = models.CharField(max_length=50) # مثلا 'otp' یا 'order_created'
    parameters = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    response_data = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    status = models.CharField(max_length=20, default="pending")
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.mobile} - {self.template_key} - {self.status}"
