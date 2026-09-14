import logging
import string

from core.integrations.sms_ir import SMSIRException, SMSIRProvider
from core.models import SmsEvent, SmsLog, SmsProviderConfig

logger = logging.getLogger(__name__)


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
            provider = self._get_provider()

            if event.send_mode == SmsEvent.SendMode.TEMPLATE:
                if not event.template_id:
                    raise SMSIRException(f"شناسه قالب رویداد «{event.label}» تنظیم نشده است.")

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
                try:
                    text = event.custom_text.format(**context)
                except (KeyError, IndexError) as exc:
                    raise SMSIRException(
                        f"پارامتر {exc} در متن رویداد «{event.label}» یافت نشد."
                    ) from exc
                response = provider.send_text(mobile=mobile, message=text)

            log.status = "sent"
            log.response_data = response
            log.save(update_fields=["status", "response_data"])
            return response

        except SMSIRException as exc:
            logger.error("SMS send failed for event=%s mobile=%s: %s", event_code, mobile, exc)
            log.status = "failed"
            log.error_message = str(exc)
            log.save(update_fields=["status", "error_message"])
            return None
        except Exception:
            logger.exception("Unexpected error sending SMS for event=%s mobile=%s", event_code, mobile)
            log.status = "failed"
            log.error_message = "خطای غیرمنتظره در ارسال پیامک."
            log.save(update_fields=["status", "error_message"])
            return None

    def _get_provider(self):
        config = SmsProviderConfig.objects.filter(is_active=True).first()
        if not config:
            raise SMSIRException("هیچ سامانه پیامکی فعالی تنظیم نشده است.")

        return SMSIRProvider(api_key=config.api_key, line_number=config.default_line_number)

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
