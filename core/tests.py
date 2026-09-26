from unittest import mock

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from core.integrations.sms_ir import SMSIRException, SMSIRProvider

from .models import SmsEvent, SmsLog, SmsProviderConfig
from .services.notifications.events import (
    COMPANY_VERIFIED,
    DEFAULT_TEXTS,
    NOTIFICATION_EVENTS,
    get_event_params,
    render_sample,
)
from .services.notifications.sms import SmsNotificationService, build_provider, validate_custom_text_params


class EventCatalogTests(TestCase):
    def test_every_registered_event_is_seeded_with_a_valid_default_text(self):
        seeded = set(SmsEvent.objects.values_list("code", flat=True))
        self.assertTrue(set(NOTIFICATION_EVENTS) <= seeded)
        for code in NOTIFICATION_EVENTS:
            self.assertIn(code, DEFAULT_TEXTS, code)
            self.assertEqual(validate_custom_text_params(DEFAULT_TEXTS[code], get_event_params(code)), set(), code)

    def test_new_events_are_seeded_disabled_so_no_credit_is_spent_by_default(self):
        self.assertFalse(SmsEvent.objects.get(code=COMPANY_VERIFIED).is_enabled)

    def test_render_sample_fills_variables(self):
        text = render_sample("{contact_name} گرامی، «{company_name}» تایید شد.", COMPANY_VERIFIED)
        self.assertNotIn("{", text)


class ProviderSelectionTests(TestCase):
    def test_only_one_provider_is_active(self):
        first = SmsProviderConfig.objects.create(name="خط-الف", api_key="key-a", is_active=True)
        second = SmsProviderConfig.objects.create(name="خط-ب", api_key="key-b", is_active=True)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(SmsProviderConfig.objects.filter(is_active=True).count(), 1)

    def test_build_provider_uses_saved_settings(self):
        config = SmsProviderConfig(name="خط", provider_type="smsir", api_key="abc", default_line_number="3000")
        with mock.patch("core.services.notifications.sms.SMSIRProvider") as provider_class:
            with mock.patch.dict(
                "core.services.notifications.sms.PROVIDER_CLASSES", {"smsir": provider_class},
            ):
                build_provider(config)
        provider_class.assert_called_once_with(api_key="abc", line_number="3000")

    def test_unknown_provider_type_is_reported(self):
        config = SmsProviderConfig(name="ناشناخته", provider_type="other", api_key="x")
        with self.assertRaises(SMSIRException):
            build_provider(config)


class NotifyTests(TestCase):
    def setUp(self):
        SmsProviderConfig.objects.all().delete()
        self.config = SmsProviderConfig.objects.create(name="فعال", api_key="live-key", is_active=True)
        self.event = SmsEvent.objects.get(code=COMPANY_VERIFIED)
        self.event.is_enabled = True
        self.event.send_mode = SmsEvent.SendMode.CUSTOM
        self.event.custom_text = "{contact_name} گرامی، حساب {company_name} فعال شد."
        self.event.save()

    def test_enabled_event_renders_dynamic_text_through_active_provider(self):
        with mock.patch.object(SMSIRProvider, "__init__", return_value=None) as init, \
                mock.patch.object(SMSIRProvider, "send_text", return_value={"status": 1}) as send_text:
            SmsNotificationService().notify(COMPANY_VERIFIED, "09123456789", {
                "contact_name": "علی", "company_name": "ترابر",
            })
        init.assert_called_once_with(api_key="live-key", line_number="")
        send_text.assert_called_once_with(mobile="09123456789", message="علی گرامی، حساب ترابر فعال شد.")
        self.assertEqual(SmsLog.objects.get(template_key=COMPANY_VERIFIED).status, "sent")

    def test_disabled_event_sends_nothing(self):
        self.event.is_enabled = False
        self.event.save()
        with mock.patch.object(SMSIRProvider, "send_text") as send_text:
            SmsNotificationService().notify(COMPANY_VERIFIED, "09123456789", {"contact_name": "a", "company_name": "b"})
        send_text.assert_not_called()
        self.assertFalse(SmsLog.objects.exists())

    def test_missing_active_provider_is_logged_as_failure(self):
        self.config.is_active = False
        self.config.save()
        SmsNotificationService().notify(COMPANY_VERIFIED, "09123456789", {"contact_name": "a", "company_name": "b"})
        log = SmsLog.objects.get(template_key=COMPANY_VERIFIED)
        self.assertEqual(log.status, "failed")
        self.assertIn("فعالی", log.error_message)


class SmsDashboardTests(TestCase):
    def setUp(self):
        SmsProviderConfig.objects.all().delete()
        self.staff = User.objects.create_user(
            mobile="09600000001", password="Pass12345!", role=User.Role.PLATFORM_ADMIN, is_staff=True,
        )
        self.client.force_login(self.staff)

    def test_add_edit_keeps_secret_key_and_switches_active_provider(self):
        self.client.post(reverse("staff_dashboard:sms_provider_add"), {
            "name": "sms.ir اصلی", "provider_type": "smsir", "api_key": "secret-1", "default_line_number": "3000",
            "is_active": "on",
        })
        main = SmsProviderConfig.objects.get(name="sms.ir اصلی")
        self.assertTrue(main.is_active)

        page = self.client.get(reverse("staff_dashboard:sms_provider_edit", args=[main.pk]))
        self.assertNotContains(page, "secret-1")  # کلید در صفحه نمایش داده نمی‌شود

        self.client.post(reverse("staff_dashboard:sms_provider_edit", args=[main.pk]), {
            "name": "sms.ir اصلی", "provider_type": "smsir", "api_key": "", "default_line_number": "3001",
            "is_active": "on",
        })
        main.refresh_from_db()
        self.assertEqual(main.api_key, "secret-1")
        self.assertEqual(main.default_line_number, "3001")

        backup = SmsProviderConfig.objects.create(name="پشتیبان", api_key="secret-2", is_active=False)
        self.client.post(reverse("staff_dashboard:sms_provider_activate", args=[backup.pk]))
        main.refresh_from_db()
        backup.refresh_from_db()
        self.assertTrue(backup.is_active)
        self.assertFalse(main.is_active)

        self.client.post(reverse("staff_dashboard:sms_provider_delete", args=[backup.pk]))
        self.assertTrue(SmsProviderConfig.objects.filter(pk=backup.pk).exists())  # فعال حذف نمی‌شود
        self.client.post(reverse("staff_dashboard:sms_provider_delete", args=[main.pk]))
        self.assertFalse(SmsProviderConfig.objects.filter(pk=main.pk).exists())

    def test_active_provider_needs_api_key(self):
        response = self.client.post(reverse("staff_dashboard:sms_provider_add"), {
            "name": "بدون کلید", "provider_type": "smsir", "api_key": "", "is_active": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SmsProviderConfig.objects.exists())

    def test_test_send_uses_that_provider_and_logs(self):
        provider = SmsProviderConfig.objects.create(name="آزمایشی", api_key="k", is_active=False)
        with mock.patch.object(SMSIRProvider, "__init__", return_value=None), \
                mock.patch.object(SMSIRProvider, "send_text", return_value={"status": 1}) as send_text:
            self.client.post(reverse("staff_dashboard:sms_provider_test", args=[provider.pk]), {
                "action": "send", "mobile": "09121112233", "message": "سلام",
            })
        send_text.assert_called_once_with(mobile="09121112233", message="سلام")
        self.assertEqual(SmsLog.objects.get(template_key="provider_test").status, "sent")

    def test_event_list_toggle_and_restore_default(self):
        response = self.client.get(reverse("staff_dashboard:sms_event_list"))
        self.assertContains(response, NOTIFICATION_EVENTS[COMPANY_VERIFIED]["label"])
        self.assertContains(response, "حمل زمینی (اعلام بار)")

        self.client.post(reverse("staff_dashboard:sms_event_toggle", args=[COMPANY_VERIFIED]))
        self.assertTrue(SmsEvent.objects.get(code=COMPANY_VERIFIED).is_enabled)
        self.client.post(reverse("staff_dashboard:sms_event_toggle", args=[COMPANY_VERIFIED]))
        self.assertFalse(SmsEvent.objects.get(code=COMPANY_VERIFIED).is_enabled)

        SmsEvent.objects.filter(code=COMPANY_VERIFIED).update(custom_text="متن دستی")
        self.client.post(reverse("staff_dashboard:sms_event_edit", args=[COMPANY_VERIFIED]), {"action": "restore_default"})
        self.assertEqual(SmsEvent.objects.get(code=COMPANY_VERIFIED).custom_text, DEFAULT_TEXTS[COMPANY_VERIFIED])

    def test_event_form_rejects_unknown_variables_and_shows_preview(self):
        url = reverse("staff_dashboard:sms_event_edit", args=[COMPANY_VERIFIED])
        page = self.client.get(url)
        self.assertContains(page, "{contact_name}")
        self.assertContains(page, "پیش‌نمایش")

        response = self.client.post(url, {
            "is_enabled": "on", "send_mode": "custom", "custom_text": "سلام {unknown_var}",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "unknown_var")
        self.assertNotEqual(SmsEvent.objects.get(code=COMPANY_VERIFIED).custom_text, "سلام {unknown_var}")
