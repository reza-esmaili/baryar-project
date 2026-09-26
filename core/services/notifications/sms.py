import logging
import string

from core.integrations.sms_ir import SMSIRException, SMSIRProvider
from core.models import SmsEvent, SmsLog, SmsProviderConfig

logger = logging.getLogger(__name__)

# پیاده‌سازی هر نوع سامانه‌ی پیامکی؛ افزودن سامانه‌ی جدید = یک کلاس با متدهای
# send_text / send_verify / get_credit + یک گزینه در SmsProviderConfig.ProviderType.
PROVIDER_CLASSES = {
    SmsProviderConfig.ProviderType.SMSIR: SMSIRProvider,
}


def build_provider(config):
    """سرویس‌گیرنده‌ی سامانه‌ی پیامکی را از روی تنظیمات ذخیره‌شده در داشبورد می‌سازد."""
    provider_class = PROVIDER_CLASSES.get(config.provider_type)
    if provider_class is None:
        raise SMSIRException(f"سامانه‌ی پیامکی «{config.get_provider_type_display()}» پیاده‌سازی نشده است.")
    return provider_class(api_key=config.api_key, line_number=config.default_line_number)


class SmsNotificationService:
    """
    نقطه ورود واحد برای ارسال پیامک رویدادمحور. پیکربندی سامانه پیامکی
    (SmsProviderConfig) و متن/قالب هر رویداد (SmsEvent) از پایگاه‌داده
    خوانده می‌شود — نه از settings.py — تا از داشبورد ادمین قابل تغییر
    باشد. هر خطایی داخلی مدیریت و در SmsLog ثبت می‌شود؛ صدا زدن این متد
    هرگز باعث شکست جریان اصلی درخواست نمی‌شود.
    """

    def notify(self, event_code, mobile, context=None):
        context = context or {}

        if not mobile:
            logger.info("SMS notify skipped: no mobile for event=%s", event_code)
            return None

        try:
            event = SmsEvent.objects.get(code=event_code)
        except SmsEvent.DoesNotExist:
            logger.warning("SMS notify skipped: unknown event code=%s", event_code)
            return None

        if not event.is_enabled:
            return None

        log = SmsLog.objects.create(
            mobile=mobile,
            template_key=event_code,
            parameters=context,
            status="pending",
        )

        try:
            # متن پیش از اتصال به سامانه ساخته می‌شود تا حتی در صورت خطای ارسال در لاگ بماند
            if event.send_mode == SmsEvent.SendMode.TEMPLATE:
                if not event.template_id:
                    raise SMSIRException(f"شناسه قالب رویداد «{event.label}» تنظیم نشده است.")
                log.message = describe_template_message(event, context)
            else:
                try:
                    log.message = event.custom_text.format(**context)
                except (KeyError, IndexError) as exc:
                    raise SMSIRException(
                        f"پارامتر {exc} در متن رویداد «{event.label}» یافت نشد."
                    ) from exc

            provider = self._get_provider()
            if event.send_mode == SmsEvent.SendMode.TEMPLATE:
                parameters = {
                    smsir_name: context[internal_key]
                    for internal_key, smsir_name in event.parameter_mapping.items()
                    if internal_key in context
                }
                response = provider.send_verify(
                    mobile=mobile,
                    template_id=event.template_id,
                    parameters=parameters,
                )
            else:
                response = provider.send_text(mobile=mobile, message=log.message)

            log.status = "sent"
            log.response_data = response
            log.save(update_fields=["status", "response_data", "message"])
            return response

        except SMSIRException as exc:
            logger.error("SMS send failed for event=%s mobile=%s: %s", event_code, mobile, exc)
            log.status = "failed"
            log.error_message = str(exc)
            log.save(update_fields=["status", "error_message", "message"])
            return None
        except Exception:
            logger.exception("Unexpected error sending SMS for event=%s mobile=%s", event_code, mobile)
            log.status = "failed"
            log.error_message = "خطای غیرمنتظره در ارسال پیامک."
            log.save(update_fields=["status", "error_message", "message"])
            return None

    def _get_provider(self):
        config = SmsProviderConfig.objects.filter(is_active=True).first()
        if not config:
            raise SMSIRException("هیچ سامانه پیامکی فعالی تنظیم نشده است.")

        return build_provider(config)

    def send_otp(self, mobile, code):
        """
        برخلاف notify() عمومی که خطاها را می‌بلعد (چون رویدادهایی مثل
        اطلاع‌رسانی سفارش نباید جریان اصلی را بشکنند)، شکست ارسال OTP باید
        به تماس‌گیرنده اطلاع داده شود — بدون کد تحویل‌شده، کل جریان
        ورود/ثبت‌نام معنا ندارد و کاربر نباید پیام «ارسال شد» ببیند.
        """
        from core.services.notifications.events import OTP_VERIFICATION

        result = self.notify(OTP_VERIFICATION, mobile, {"code": code})
        if result is None:
            raise SMSIRException("ارسال پیامک کد تایید ناموفق بود.")
        return result


def describe_template_message(event, context):
    """
    متن پیامک‌های قالبی در پنل sms.ir تعریف شده و این‌جا در دسترس نیست؛ برای لاگ،
    شناسه‌ی قالب و مقدار متغیرها با عنوان فارسی‌شان ثبت می‌شود.
    """
    from core.services.notifications.events import get_event_params

    labels = get_event_params(event.code)
    values = "، ".join(f"{labels.get(key, key)}: {value}" for key, value in context.items())
    return f"قالب sms.ir شماره {event.template_id}" + (f" — {values}" if values else "")


def validate_custom_text_params(text, allowed_keys):
    """
    تمام {پارامتر}های استفاده‌شده در متن دلخواه را استخراج می‌کند و آن‌هایی
    که جزو پارامترهای مجاز رویداد نیستند را برمی‌گرداند (برای اعتبارسنجی
    فرم پیش از ذخیره).
    """
    used = set()
    for _, field_name, _, _ in string.Formatter().parse(text):
        if field_name:
            used.add(field_name)

    return used - set(allowed_keys)
