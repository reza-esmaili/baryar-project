from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import IdentityDocument, User
from core.models import SmsLog
from documents.models import DocumentType
from land_freight.models import LandCarrierProfile, VehicleType
from locations.models import City, Country, Province

from .models import CompanyDocumentRequirement, ForwarderCompany, ServiceCategory
from .services import (
    approve_registration,
    document_checklist,
    is_company_fully_documented,
    recompute_company_verification,
    registration_state,
    reject_registration,
)


def pdf(name="doc.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 test", content_type="application/pdf")


class RemoveUploadedFilesMixin:
    """فایل‌های بارگذاری‌شده در آزمون‌ها از محل ذخیره‌ی محافظت‌شده پاک می‌شوند."""

    def tearDown(self):
        for doc in IdentityDocument.objects.exclude(file=""):
            doc.file.delete(save=False)
        super().tearDown()


class RequirementFixtures(RemoveUploadedFilesMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        # قوانین seed شده کنار گذاشته می‌شوند تا آزمون‌ها به داده‌ی مهاجرت وابسته نباشند.
        CompanyDocumentRequirement.objects.all().delete()
        cls.general = DocumentType.objects.create(code="t-general", title="مدرک-عمومی-آزمون")
        cls.air_license = DocumentType.objects.create(code="t-air", title="مجوز-هوایی-آزمون")
        cls.road_license = DocumentType.objects.create(code="t-road", title="مجوز-جاده‌ای-آزمون")
        cls.insurance = DocumentType.objects.create(code="t-insurance", title="بیمه-آزمون")
        cls.inactive_type = DocumentType.objects.create(code="t-inactive", title="غیرفعال-آزمون")

        CompanyDocumentRequirement.objects.create(document_type=cls.general, service=ServiceCategory.ALL)
        CompanyDocumentRequirement.objects.create(document_type=cls.air_license, service=ServiceCategory.AIR)
        CompanyDocumentRequirement.objects.create(document_type=cls.road_license, service=ServiceCategory.LAND_DOMESTIC)
        CompanyDocumentRequirement.objects.create(
            document_type=cls.insurance, service=ServiceCategory.LAND_DOMESTIC, is_required=False,
        )
        CompanyDocumentRequirement.objects.create(
            document_type=cls.inactive_type, service=ServiceCategory.AIR, is_active=False,
        )

    def make_company(self, mobile, verified=False, active=False, **flags):
        user = User.objects.create_user(
            mobile=mobile, password="Pass12345!", role=User.Role.FORWARDER_ADMIN,
            first_name="نماینده", last_name="آزمون",
        )
        return ForwarderCompany.objects.create(
            admin_user=user, company_name=f"شرکت-آزمون-{mobile}", company_type="other",
            national_id=mobile[-11:].rjust(11, "7"), registration_number=f"r{mobile}",
            ceo_first_name="م", ceo_last_name="ع", ceo_national_code="0012345678",
            phone="02100000000", email=f"{mobile}@example.com", postal_code="1234567890",
            address="آدرس", is_verified=verified, is_active=active, **flags,
        )

    def upload(self, company, document_type, status=IdentityDocument.Status.PENDING):
        return IdentityDocument.objects.create(
            user=company.admin_user, company=company, document_type=document_type, file=pdf(), status=status,
        )


class RequirementRuleTests(RequirementFixtures):
    def test_requirements_follow_company_categories(self):
        company = self.make_company("09400000001", service_air=True)
        titles = {item["document_type"].title for item in document_checklist(company)}
        self.assertEqual(titles, {"مدرک-عمومی-آزمون", "مجوز-هوایی-آزمون"})

        company.service_air = False
        company.service_land_domestic = True
        titles = {item["document_type"].title for item in document_checklist(company)}
        self.assertEqual(titles, {"مدرک-عمومی-آزمون", "مجوز-جاده‌ای-آزمون", "بیمه-آزمون"})

    def test_verification_needs_every_required_document_approved(self):
        company = self.make_company("09400000002", service_land_domestic=True)
        approved = IdentityDocument.Status.APPROVED
        self.upload(company, self.general, approved)
        self.assertFalse(is_company_fully_documented(company))

        self.upload(company, self.road_license, approved)
        # بیمه اختیاری است و نبودنش مانع تایید نیست
        self.assertTrue(is_company_fully_documented(company))

    def test_latest_upload_of_a_type_decides(self):
        company = self.make_company("09400000003", service_air=True)
        self.upload(company, self.general, IdentityDocument.Status.APPROVED)
        self.upload(company, self.air_license, IdentityDocument.Status.APPROVED)
        self.assertTrue(is_company_fully_documented(company))

        self.upload(company, self.air_license, IdentityDocument.Status.PENDING)  # نسخه‌ی تازه، هنوز بررسی نشده
        self.assertFalse(is_company_fully_documented(company))

    def test_recompute_verifies_and_activates_once(self):
        company = self.make_company("09400000004", service_air=True)
        self.upload(company, self.general, IdentityDocument.Status.APPROVED)
        self.upload(company, self.air_license, IdentityDocument.Status.APPROVED)

        self.assertTrue(recompute_company_verification(company))
        company.refresh_from_db()
        self.assertTrue(company.is_verified and company.is_active)
        self.assertFalse(recompute_company_verification(company))

    def test_registration_state(self):
        company = self.make_company("09400000005", service_air=True)
        self.assertEqual(registration_state(company), "incomplete")
        self.upload(company, self.general)
        self.assertEqual(registration_state(company), "pending")
        self.upload(company, self.air_license, IdentityDocument.Status.REJECTED)
        self.assertEqual(registration_state(company), "rejected")


class RegistrationFlowTests(RequirementFixtures):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.iran = Country.objects.filter(code="IRN").first() or Country.objects.create(name="ایران-آزمون", code="IRN")
        cls.province = Province.objects.create(country=cls.iran, name="استان-ثبت‌نام-آزمون")
        cls.city = City.objects.create(province=cls.province, name="شهر-ثبت‌نام-آزمون")
        cls.truck = VehicleType.objects.create(name="ناوگان-ثبت‌نام-آزمون", capacity_kg=8000)

    def setUp(self):
        self.user = User.objects.create_user(
            mobile="09410000001", password="Pass12345!", role=User.Role.FORWARDER_ADMIN,
            first_name="سارا", last_name="آزمون",
        )
        self.client.force_login(self.user)

    def payload(self, **overrides):
        data = {
            "applicant_role": "ceo",
            "company_name": "باربری آزمون",
            "company_type": "other",
            "national_id": "14000000001",
            "registration_number": "55555",
            "phone": "02188888888",
            "email": "reg@example.com",
            "postal_code": "1234567890",
            "address": "تهران، آزمون",
            "ceo_national_code": "0012345678",
            "services": ["service_land_domestic"],
            "land_vehicle_types": [self.truck.pk],
            f"doc_{self.general.pk}": pdf("general.pdf"),
            f"doc_{self.road_license.pk}": pdf("road.pdf"),
        }
        data.update(overrides)
        return data

    def test_documents_page_lists_every_defined_requirement(self):
        response = self.client.get(reverse("forwarder_panel:documents"))
        self.assertEqual(response.status_code, 200)
        for title in ("مدرک-عمومی-آزمون", "مجوز-هوایی-آزمون", "مجوز-جاده‌ای-آزمون", "بیمه-آزمون"):
            self.assertContains(response, title)
        self.assertNotContains(response, "غیرفعال-آزمون")

    def test_submit_creates_pending_company_with_typed_documents_and_land_area(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("forwarder_panel:documents"), self.payload())
        self.assertRedirects(response, reverse("forwarder_panel:documents"), fetch_redirect_response=False)

        company = ForwarderCompany.objects.get(admin_user=self.user)
        self.assertTrue(company.service_land_domestic)
        self.assertFalse(company.is_verified or company.is_active)
        self.assertEqual(
            set(company.identity_documents.values_list("document_type__code", flat=True)),
            {"t-general", "t-road"},
        )
        profile = LandCarrierProfile.objects.get(company=company)
        self.assertEqual(list(profile.vehicle_types.all()), [self.truck])
        # رویداد «دریافت مدارک» اجرا شد (غیرفعال است، پس پیامکی ثبت نمی‌شود)
        self.assertFalse(SmsLog.objects.filter(template_key="company_registration_received").exists())

    def test_missing_required_document_for_selected_category_is_rejected(self):
        payload = self.payload()
        payload.pop(f"doc_{self.road_license.pk}")
        response = self.client.post(reverse("forwarder_panel:documents"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "این مدرک برای دسته‌های انتخابی الزامی است")
        self.assertFalse(ForwarderCompany.objects.filter(admin_user=self.user).exists())

    def test_land_categories_need_fleet_and_intracity_needs_cities(self):
        payload = self.payload(services=["service_land_intracity"], land_vehicle_types=[])
        response = self.client.post(reverse("forwarder_panel:documents"), payload)
        self.assertContains(response, "حداقل یک شهر تحت پوشش")
        self.assertContains(response, "حداقل یک نوع ناوگان")

    def test_wrong_file_type_is_rejected(self):
        payload = self.payload(**{f"doc_{self.general.pk}": SimpleUploadedFile("x.exe", b"MZ")})
        response = self.client.post(reverse("forwarder_panel:documents"), payload)
        self.assertContains(response, "فرمت فایل مجاز نیست")


class StaffRegistrationReviewTests(RequirementFixtures):
    def setUp(self):
        self.staff = User.objects.create_user(
            mobile="09420000001", password="Pass12345!", role=User.Role.PLATFORM_ADMIN, is_staff=True,
        )
        self.client.force_login(self.staff)
        self.company = self.make_company("09420000002", service_land_domestic=True)
        self.upload(self.company, self.general)
        self.upload(self.company, self.road_license)
        self.air_company = self.make_company("09420000003", verified=True, active=True, service_air=True)

    def test_queue_lists_pending_companies_and_filters_by_category(self):
        url = reverse("staff_dashboard:registration_queue")
        response = self.client.get(url)
        self.assertContains(response, self.company.company_name)
        self.assertNotContains(response, self.air_company.company_name)  # تایید‌شده در صف نیست

        response = self.client.get(url, {"service": "air"})
        self.assertNotContains(response, self.company.company_name)
        response = self.client.get(url, {"service": "land_domestic", "state": "pending"})
        self.assertContains(response, self.company.company_name)

    def test_company_list_filters_by_service_category(self):
        url = reverse("staff_dashboard:forwarder_list")
        response = self.client.get(url, {"service": "air"})
        self.assertContains(response, self.air_company.company_name)
        self.assertNotContains(response, self.company.company_name)

    def test_detail_shows_registration_info_and_checklist(self):
        response = self.client.get(reverse("staff_dashboard:forwarder_detail", args=[self.company.pk]))
        self.assertContains(response, "بررسی درخواست ثبت‌نام")
        self.assertContains(response, "مجوز-جاده‌ای-آزمون")
        self.assertContains(response, self.company.registration_number)

    def test_approve_verifies_activates_and_approves_pending_documents(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("staff_dashboard:registration_decision", args=[self.company.pk]), {"action": "approve"},
            )
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_verified and self.company.is_active)
        self.assertFalse(self.company.identity_documents.exclude(status=IdentityDocument.Status.APPROVED).exists())

    def test_reject_needs_reason_and_marks_pending_documents_rejected(self):
        url = reverse("staff_dashboard:registration_decision", args=[self.company.pk])
        self.client.post(url, {"action": "reject", "reason": ""})
        self.assertFalse(self.company.identity_documents.filter(status=IdentityDocument.Status.REJECTED).exists())

        self.client.post(url, {"action": "reject", "reason": "تصویر ناخوانا است"})
        rejected = self.company.identity_documents.filter(status=IdentityDocument.Status.REJECTED)
        self.assertEqual(rejected.count(), 2)
        self.assertEqual(rejected.first().admin_note, "تصویر ناخوانا است")
        self.assertEqual(registration_state(self.company), "rejected")

    def test_services_approve_and_reject_directly(self):
        reject_registration(self.company, "نیاز به اصلاح")
        self.company.refresh_from_db()
        self.assertFalse(self.company.is_verified)
        self.upload(self.company, self.general)
        self.upload(self.company, self.road_license)
        approve_registration(self.company)
        self.assertTrue(is_company_fully_documented(self.company))

    def test_requirements_are_manageable_from_lookup_engine(self):
        url = reverse("staff_dashboard:lookup_add", args=["company-document-requirements"])
        response = self.client.post(url, {
            "document_type": self.insurance.pk, "service": "sea", "is_required": "on",
            "guidance": "بیمه‌نامه‌ی معتبر", "sort_order": 5, "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CompanyDocumentRequirement.objects.filter(document_type=self.insurance, service="sea").exists())

        # تکراری (همان مدرک و همان دسته) پذیرفته نمی‌شود
        response = self.client.post(url, {
            "document_type": self.insurance.pk, "service": "sea", "sort_order": 1, "is_active": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CompanyDocumentRequirement.objects.filter(document_type=self.insurance, service="sea").count(), 1)
