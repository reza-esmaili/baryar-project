from datetime import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import IdentityDocument, User
from forwarders.models import ForwarderCompany


class UserListAndDeleteTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            mobile="09700000001", password="Pass12345!", role=User.Role.PLATFORM_ADMIN, is_staff=True,
            first_name="مدیر", last_name="آزمون",
        )
        self.customer = User.objects.create_user(
            mobile="09700000002", password="Pass12345!", role=User.Role.CUSTOMER,
            first_name="مریم", last_name="آزمون",
        )
        User.objects.filter(pk=self.customer.pk).update(created_at=datetime(2026, 9, 26, 14, 30))
        self.client.force_login(self.staff)

    def tearDown(self):
        for doc in IdentityDocument.objects.exclude(file=""):
            doc.file.delete(save=False)

    def test_list_shows_jalali_join_date_and_role_tabs(self):
        response = self.client.get(reverse("staff_dashboard:user_list"))
        self.assertContains(response, "1405/07/04")  # ۲۶ سپتامبر ۲۰۲۶
        self.assertNotContains(response, "2026/09/26")
        self.assertContains(response, "مشتری")
        self.assertContains(response, reverse("staff_dashboard:user_delete", args=[self.customer.pk]))
        # دکمه‌ی حذف برای حساب خود کارشناس نمایش داده نمی‌شود
        self.assertNotContains(response, reverse("staff_dashboard:user_delete", args=[self.staff.pk]))

    def test_role_and_status_filters(self):
        response = self.client.get(reverse("staff_dashboard:user_list"), {"role": "customer"})
        self.assertEqual([u.pk for u in response.context["page_obj"]], [self.customer.pk])
        User.objects.filter(pk=self.customer.pk).update(is_active=False)
        response = self.client.get(reverse("staff_dashboard:user_list"), {"status": "active"})
        self.assertNotIn(self.customer.pk, [u.pk for u in response.context["page_obj"]])

    def test_confirm_page_lists_what_is_deleted_and_post_deletes_with_files(self):
        doc = IdentityDocument.objects.create(
            user=self.customer, doc_type=IdentityDocument.DocType.NATIONAL_CARD,
            file=SimpleUploadedFile("card.pdf", b"%PDF-1.4", content_type="application/pdf"),
        )
        storage, name = doc.file.storage, doc.file.name
        url = reverse("staff_dashboard:user_delete", args=[self.customer.pk])

        page = self.client.get(url)
        self.assertContains(page, "مدارک هویتی")
        self.assertContains(page, "حذف قطعی کاربر")

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url)
        self.assertRedirects(response, reverse("staff_dashboard:user_list"), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(pk=self.customer.pk).exists())
        self.assertFalse(IdentityDocument.objects.filter(pk=doc.pk).exists())
        self.assertFalse(storage.exists(name))

    def test_cannot_delete_self(self):
        response = self.client.post(reverse("staff_dashboard:user_delete", args=[self.staff.pk]))
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())
        self.assertRedirects(response, reverse("staff_dashboard:user_delete", args=[self.staff.pk]), fetch_redirect_response=False)

    def test_company_admin_is_protected(self):
        admin = User.objects.create_user(mobile="09700000003", password="Pass12345!", role=User.Role.FORWARDER_ADMIN)
        ForwarderCompany.objects.create(
            admin_user=admin, company_name="شرکت-حذف-آزمون", company_type="other",
            national_id="70000000003", registration_number="r700", ceo_first_name="م", ceo_last_name="ع",
            ceo_national_code="0012345678", phone="02100000000", email="del@example.com",
            postal_code="1234567890", address="آدرس",
        )
        url = reverse("staff_dashboard:user_delete", args=[admin.pk])
        page = self.client.get(url)
        self.assertContains(page, "قابل حذف نیست")
        self.assertContains(page, "شرکت-حذف-آزمون")
        self.client.post(url)
        self.assertTrue(User.objects.filter(pk=admin.pk).exists())

    def test_non_staff_cannot_delete(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse("staff_dashboard:user_delete", args=[self.staff.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())


class OrderTransportStepTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(mobile="09700000010", password="Pass12345!", role=User.Role.CUSTOMER)
        self.client.force_login(self.user)

    def test_order_page_starts_with_transport_type_step(self):
        response = self.client.get(reverse("orders:create_request"))
        self.assertContains(response, 'id="step-0"')
        for value in ("air", "sea", "land"):
            self.assertContains(response, f'name="transport_family" value="{value}"')
        for scope in ("intracity", "domestic", "international"):
            self.assertContains(response, f'name="land_scope" value="{scope}"')
        self.assertContains(response, reverse("land_freight:request_create"))

    def test_mode_query_presets_transport_mode(self):
        response = self.client.get(reverse("orders:create_request"), {"mode": "lcl"})
        self.assertEqual(response.context["form"].initial.get("transport_mode"), "sea_lcl")
