from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from forwarders.models import ForwarderCompany, ForwarderStaff
from land_freight.models import LandCarrierProfile, VehicleType


class PanelAccessTests(TestCase):
    """آیتم‌ها و دسترسی‌های پنل /panel/ بر اساس دسته‌ی خدمات و وضعیت شرکت."""

    @classmethod
    def setUpTestData(cls):
        cls.truck = VehicleType.objects.create(name="ناوگان-پنل-آزمون", capacity_kg=5000)

    def setUp(self):
        cache.clear()

    def make_company(self, mobile, verified=True, active=True, **flags):
        user = User.objects.create_user(mobile=mobile, password="Pass12345!", role=User.Role.FORWARDER_ADMIN)
        company = ForwarderCompany.objects.create(
            admin_user=user, company_name=f"شرکت-پنل-{mobile}", company_type="other",
            national_id=mobile[-11:].rjust(11, "3"), registration_number=f"p{mobile}",
            ceo_first_name="م", ceo_last_name="ع", ceo_national_code="0012345678",
            phone="02100000000", email=f"{mobile}@example.com", postal_code="1234567890",
            address="آدرس", is_verified=verified, is_active=active, **flags,
        )
        profile = LandCarrierProfile.objects.create(company=company)
        profile.vehicle_types.set([self.truck])
        return company

    def test_land_only_company_sees_land_items_and_no_rate_items(self):
        company = self.make_company("09500000001", service_land_domestic=True)
        self.client.force_login(company.admin_user)

        response = self.client.get(reverse("forwarder_panel:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اعلام بار زمینی")
        self.assertContains(response, reverse("forwarder_panel:land_request_list"))
        self.assertNotContains(response, reverse("forwarder_panel:rate_list"))
        self.assertNotContains(response, reverse("forwarder_panel:order_list"))
        self.assertNotContains(response, "سفارشات ثبت شده")

        for name in ("rate_list", "order_list", "report_page"):
            response = self.client.get(reverse(f"forwarder_panel:{name}"))
            self.assertRedirects(response, reverse("forwarder_panel:land_request_list"), fetch_redirect_response=False)

    def test_air_company_sees_rate_items_and_no_land_items(self):
        company = self.make_company("09500000002", service_air=True)
        self.client.force_login(company.admin_user)

        response = self.client.get(reverse("forwarder_panel:dashboard"))
        self.assertContains(response, reverse("forwarder_panel:rate_list"))
        self.assertContains(response, "سفارشات ثبت شده")
        self.assertNotContains(response, reverse("forwarder_panel:land_request_list"))

        self.assertEqual(self.client.get(reverse("forwarder_panel:rate_list")).status_code, 200)
        response = self.client.get(reverse("forwarder_panel:land_request_list"))
        self.assertRedirects(response, reverse("forwarder_panel:dashboard"), fetch_redirect_response=False)

    def test_mixed_company_sees_both_sections(self):
        company = self.make_company("09500000003", service_sea=True, service_land_international=True)
        self.client.force_login(company.admin_user)
        response = self.client.get(reverse("forwarder_panel:dashboard"))
        self.assertContains(response, reverse("forwarder_panel:rate_list"))
        self.assertContains(response, reverse("forwarder_panel:land_request_list"))
        self.assertContains(response, "سفارش‌های هوایی و دریایی")

    def test_unverified_company_only_reaches_registration(self):
        company = self.make_company("09500000004", verified=False, active=False, service_air=True)
        self.client.force_login(company.admin_user)

        response = self.client.get(reverse("forwarder_panel:dashboard"))
        self.assertRedirects(response, reverse("forwarder_panel:documents"), fetch_redirect_response=False)

        page = self.client.get(reverse("forwarder_panel:documents"))
        self.assertContains(page, "ثبت‌نام و مدارک شرکت")
        self.assertContains(page, "در انتظار تایید")
        self.assertNotContains(page, reverse("forwarder_panel:rate_list"))
        self.assertNotContains(page, 'href="' + reverse("forwarder_panel:dashboard") + '"')

    def test_deactivated_company_is_locked_out(self):
        company = self.make_company("09500000005", verified=True, active=False, service_land_domestic=True)
        self.client.force_login(company.admin_user)
        response = self.client.get(reverse("forwarder_panel:land_request_list"))
        self.assertRedirects(response, reverse("forwarder_panel:documents"), fetch_redirect_response=False)
        page = self.client.get(reverse("forwarder_panel:documents"))
        self.assertContains(page, "غیرفعال")

    def test_staff_of_inactive_company_sees_status_page_instead_of_403(self):
        company = self.make_company("09500000006", verified=False, active=False, service_air=True)
        staff_user = User.objects.create_user(
            mobile="09500000007", password="Pass12345!", role=User.Role.FORWARDER_EXPERT,
        )
        ForwarderStaff.objects.create(company=company, user=staff_user, national_code="0012345679")
        self.client.force_login(staff_user)

        response = self.client.get(reverse("forwarder_panel:documents"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "حساب شرکت هنوز فعال نشده است")
