import logging

from sms_ir import SmsIr

logger = logging.getLogger(__name__)


class SMSIRException(Exception):
    pass


class SMSIRProvider:
    """
    لایه نازک روی SDK رسمی sms.ir (پکیج smsir-python —
    https://github.com/IPeCompany/SmsPanelV2.Python) — کلید API و شماره خط
    از پایگاه‌داده (SmsProviderConfig) خوانده می‌شوند، نه از settings.py.
    """

    def __init__(self, api_key, line_number=None):
        if not api_key:
            raise SMSIRException("کلید API سرویس پیامک تنظیم نشده است.")

        self._client = SmsIr(api_key=api_key, linenumber=line_number or None)

    def send_text(self, mobile, message, line_number=None):
        """ارسال پیامک متن آزاد (بدون قالب تاییدشده)."""
        response = self._client.send_sms(
            number=mobile,
            message=message,
            linenumber=line_number or None,
        )
        return self._handle_response(response)

    def send_verify(self, mobile, template_id, parameters):
        """
        ارسال با قالب تاییدشده sms.ir (سرویس Verify).

        parameters: دیکشنری {نام‌پارامتر_در_قالب_sms.ir: مقدار}
        """
        if not template_id:
            raise SMSIRException("شناسه قالب پیامک تنظیم نشده است.")

        payload = [
            {"name": name, "value": str(value)}
            for name, value in parameters.items()
        ]

        response = self._client.send_verify_code(
            number=mobile,
            template_id=int(template_id),
            parameters=payload,
        )
        return self._handle_response(response)

    def get_credit(self):
        return self._handle_response(self._client.get_credit())

    def _handle_response(self, response):
        if response.status_code < 200 or response.status_code >= 300:
            logger.error(
                "SMS.ir request failed. status=%s response=%s",
                response.status_code,
                response.text,
            )
            raise SMSIRException(
                f"خطا در ارسال پیامک. status={response.status_code}, response={response.text}"
            )

        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}
