from celery import shared_task


@shared_task(ignore_result=True)
def notify_task(event_code, mobile, context=None):
    """
    نسخه غیرمسدودکننده SmsNotificationService.notify() برای رویدادهای
    چرخه‌عمر سفارش (ثبت سفارش، تطبیق نرخ، نهایی‌شدن سفارش، درخواست مدرک) —
    این رویدادها نباید پاسخ به کاربر را معطل ارسال پیامک نگه دارند. OTP از
    این مسیر رد نمی‌شود چون send_otp() باید همزمان و با گزارش خطا اجرا شود.
    """
    from core.services.notifications.sms import SmsNotificationService

    SmsNotificationService().notify(event_code, mobile, context)
