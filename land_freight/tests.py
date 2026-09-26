from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from documents.models import DocumentRequirementLevel, DocumentRule, DocumentType
from forwarders.models import ForwarderCompany
from locations.models import City, Country, DestinationCity, Port, Province
from orders.models import CustomerNotification, ForwarderNotification
from rates.models import CargoType, TransportMode

from .models import (
    DispatchStatus,
    InternationalDirection,
    LandCarrierProfile,
    LandDocumentStatus,
    LandFreightRequest,
    LandRequestDocument,
    LandRequestStatus,
    LandServiceScope,
    VehicleType,
    local_today,
)
from .services import (
    LandRequestError,
    accept_request,
    cancel_request,
    decline_request,
    eligible_carriers,
    expire_stale_requests,
    publish_request,
    republish_request,
    update_carrier_status,
)


class LandFreightFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.iran = Country.objects.filter(code="IRN").first() or Country.objects.create(name="ایران-آزمون", code="IRN")
        cls.turkey = Country.objects.create(name="کشور-آزمون-الف", code="TSA")
        cls.iraq = Country.objects.create(name="کشور-آزمون-ب", code="TSB")
        cls.province = Province.objects.create(country=cls.iran, name="استان-آزمون-زمینی")
        cls.city_a = City.objects.create(province=cls.province, name="شهر-آزمون-الف")
        cls.city_b = City.objects.create(province=cls.province, name="شهر-آزمون-ب")
        cls.foreign_city = DestinationCity.objects.create(country=cls.turkey, name="شهر-خارجی-آزمون")
        cls.border = Port.objects.create(city=cls.foreign_city, name="مرز-آزمون", port_type="land")
        cls.cargo_type = CargoType.objects.create(name="کالای-آزمون-زمینی", transport_mode=TransportMode.LAND)
        cls.nissan = VehicleType.objects.create(name="ناوگان-آزمون-سبک", capacity_kg=1500)
        cls.trailer = VehicleType.objects.create(name="ناوگان-آزمون-سنگین", capacity_kg=25000)
        cls.customer = User.objects.create_user(
            mobile="09350000001", password="Pass12345!", role=User.Role.CUSTOMER,
            first_name="مشتری", last_name="آزمون",
        )

    @classmethod
    def make_company(cls, mobile, *, vehicles=(), cities=(), countries=(), verified=True, **flags):
        user = User.objects.create_user(mobile=mobile, password="Pass12345!", role=User.Role.FORWARDER_ADMIN)
        company = ForwarderCompany.objects.create(
            admin_user=user, company_name=f"شرکت {mobile}", company_type="other",
            national_id=mobile[-11:].rjust(11, "1"), registration_number=mobile,
            ceo_first_name="م", ceo_last_name="ع", ceo_national_code="0012345678",
            phone="02100000000", email=f"{mobile}@example.com", postal_code="1234567890",
            address="آدرس", is_verified=verified, is_active=True, **flags,
        )
        profile = LandCarrierProfile.objects.create(company=company)
        profile.vehicle_types.set(vehicles)
        profile.service_cities.set(cities)
        profile.service_countries.set(countries)
        return company

    def make_request(self, scope=LandServiceScope.DOMESTIC, **overrides):
        data = dict(
            customer=self.customer, scope=scope,
            origin_city=self.city_a, destination_city=self.city_b,
            pickup_address="مبدا", delivery_address="مقصد",
            pickup_date=local_today() + timedelta(days=1),
            cargo_type=self.cargo_type, cargo_description="آزمون", weight_kg=Decimal("800"),
            vehicle_type=self.nissan, sender_name="الف", sender_phone="09120000000",
            receiver_name="ب", receiver_phone="09120000001",
            proposed_price=Decimal("50000000"),
            expires_at=LandFreightRequest.default_expiry(scope),
        )
        data.update(overrides)
        return LandFreightRequest.objects.create(**data)


class EligibilityTests(LandFreightFixtures):
    def test_intracity_only_carriers_serving_that_city_with_matching_vehicle(self):
        match = self.make_company("09110000001", service_land_intracity=True, vehicles=[self.nissan], cities=[self.city_a])
        self.make_company("09110000002", service_land_intracity=True, vehicles=[self.nissan], cities=[self.city_b])
        self.make_company("09110000003", service_land_intracity=True, vehicles=[self.trailer], cities=[self.city_a])
        self.make_company("09110000004", service_land_domestic=True, vehicles=[self.nissan])
        self.make_company("09110000005", service_land_intracity=True, vehicles=[self.nissan],
                          cities=[self.city_a], verified=False)

        req = self.make_request(LandServiceScope.INTRACITY, destination_city=self.city_a)
        self.assertEqual(list(eligible_carriers(req)), [match])

    def test_domestic_covers_all_of_iran(self):
        domestic = self.make_company("09110000011", service_land_domestic=True, vehicles=[self.nissan])
        self.make_company("09110000012", service_land_intracity=True, vehicles=[self.nissan], cities=[self.city_a])

        req = self.make_request(LandServiceScope.DOMESTIC)
        self.assertEqual(list(eligible_carriers(req)), [domestic])

    def test_international_respects_country_coverage_and_empty_means_all(self):
        covers_turkey = self.make_company("09110000021", service_land_international=True,
                                          vehicles=[self.nissan], countries=[self.turkey])
        covers_all = self.make_company("09110000022", service_land_international=True, vehicles=[self.nissan])
        self.make_company("09110000023", service_land_international=True, vehicles=[self.nissan], countries=[self.iraq])

        req = self.make_request(
            LandServiceScope.INTERNATIONAL, direction=InternationalDirection.EXPORT,
            destination_city=None, foreign_country=self.turkey, foreign_city=self.foreign_city,
        )
        self.assertEqual(set(eligible_carriers(req)), {covers_turkey, covers_all})


class LifecycleTests(LandFreightFixtures):
    def setUp(self):
        self.first = self.make_company("09120000101", service_land_domestic=True, vehicles=[self.nissan])
        self.second = self.make_company("09120000102", service_land_domestic=True, vehicles=[self.nissan])
        self.request = self.make_request()
        self.dispatched = publish_request(self.request, self.customer)

    def test_publish_dispatches_and_notifies_every_eligible_carrier(self):
        self.assertEqual(self.dispatched, 2)
        self.assertEqual(self.request.dispatches.filter(status=DispatchStatus.SENT).count(), 2)
        self.assertEqual(
            ForwarderNotification.objects.filter(notif_type=ForwarderNotification.NotifType.LAND_REQUEST).count(), 2,
        )

    def test_first_accept_wins_and_second_is_rejected(self):
        won = accept_request(self.request.pk, self.first, self.first.admin_user, self.request.proposed_price)
        self.assertEqual(won.status, LandRequestStatus.ASSIGNED)
        self.assertEqual(won.assigned_company, self.first)
        self.assertEqual(won.agreed_price, self.request.proposed_price)

        with self.assertRaisesMessage(LandRequestError, "زودتر"):
            accept_request(self.request.pk, self.second, self.second.admin_user, self.request.proposed_price)

        statuses = dict(self.request.dispatches.values_list("company_id", "status"))
        self.assertEqual(statuses[self.first.id], DispatchStatus.ACCEPTED)
        self.assertEqual(statuses[self.second.id], DispatchStatus.MISSED)
        self.assertTrue(CustomerNotification.objects.filter(user=self.customer).exists())

    def test_accept_is_refused_when_price_changed_after_carrier_viewed_it(self):
        with self.assertRaisesMessage(LandRequestError, "تغییر کرده"):
            accept_request(self.request.pk, self.first, self.first.admin_user, Decimal("1"))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, LandRequestStatus.OPEN)

    def test_company_not_dispatched_cannot_accept(self):
        outsider = self.make_company("09120000103", service_land_domestic=True, vehicles=[self.trailer])
        with self.assertRaisesMessage(LandRequestError, "ارسال نشده"):
            accept_request(self.request.pk, outsider, outsider.admin_user, self.request.proposed_price)

    def test_expired_request_cannot_be_accepted_and_gets_closed(self):
        LandFreightRequest.objects.filter(pk=self.request.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        with self.assertRaisesMessage(LandRequestError, "مهلت"):
            accept_request(self.request.pk, self.first, self.first.admin_user, self.request.proposed_price)

        self.assertEqual(expire_stale_requests(), 1)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, LandRequestStatus.EXPIRED)
        self.assertFalse(self.request.dispatches.exclude(status=DispatchStatus.CLOSED).exists())

    def test_republish_reopens_with_new_price_and_resets_dispatches(self):
        LandFreightRequest.objects.filter(pk=self.request.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        expire_stale_requests()

        count = republish_request(self.request, self.customer, Decimal("65000000"))
        self.request.refresh_from_db()
        self.assertEqual(count, 2)
        self.assertEqual(self.request.status, LandRequestStatus.OPEN)
        self.assertEqual(self.request.proposed_price, Decimal("65000000"))
        self.assertGreater(self.request.expires_at, timezone.now())
        self.assertEqual(self.request.dispatches.filter(status=DispatchStatus.SENT).count(), 2)

    def test_carrier_status_flow_and_cancel_rules(self):
        accept_request(self.request.pk, self.first, self.first.admin_user, self.request.proposed_price)
        self.request.refresh_from_db()

        with self.assertRaises(LandRequestError):
            update_carrier_status(self.request, self.second, self.second.admin_user, LandRequestStatus.IN_TRANSIT)

        update_carrier_status(self.request, self.first, self.first.admin_user, LandRequestStatus.IN_TRANSIT)
        with self.assertRaisesMessage(LandRequestError, "قابل لغو نیست"):
            cancel_request(self.request, self.customer, "تغییر برنامه")

        update_carrier_status(self.request, self.first, self.first.admin_user, LandRequestStatus.DELIVERED)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, LandRequestStatus.DELIVERED)

    def test_customer_can_cancel_open_request(self):
        cancel_request(self.request, self.customer, "نیازی نیست")
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, LandRequestStatus.CANCELLED)
        self.assertFalse(self.request.dispatches.exclude(status=DispatchStatus.CLOSED).exists())


class EndToEndViewTests(LandFreightFixtures):
    def test_customer_posts_request_forwarder_accepts_customer_sees_carrier(self):
        carrier = self.make_company("09130000001", service_land_domestic=True, vehicles=[self.nissan])

        self.client.force_login(self.customer)
        response = self.client.post(reverse("land_freight:request_create"), {
            "scope": "domestic",
            "origin_province": self.province.pk, "origin_city": self.city_a.pk,
            "destination_province": self.province.pk, "destination_city": self.city_b.pk,
            "pickup_address": "انبار ۱", "delivery_address": "انبار ۲",
            "pickup_date": (local_today() + timedelta(days=2)).isoformat(),
            "pickup_window": "any",
            "cargo_type": self.cargo_type.pk, "cargo_description": "کارتن", "weight_kg": "900",
            "packaging_type": "carton", "vehicle_type": self.nissan.pk,
            "sender_name": "الف", "sender_phone": "۰۹۱۲۰۰۰۰۰۰۰",
            "receiver_name": "ب", "receiver_phone": "09120000001",
            "proposed_price": "45000000",
        })
        land_request = LandFreightRequest.objects.get(customer=self.customer)
        self.assertRedirects(response, reverse("land_freight:request_detail", args=[land_request.pk]))
        self.assertEqual(land_request.sender_phone, "09120000000")
        self.assertEqual(land_request.dispatches.count(), 1)

        self.client.force_login(carrier.admin_user)
        inbox = self.client.get(reverse("forwarder_panel:land_request_list"))
        self.assertContains(inbox, land_request.reference)

        detail = self.client.get(reverse("forwarder_panel:land_request_detail", args=[land_request.pk]))
        self.assertNotContains(detail, "انبار ۱")  # آدرس دقیق تا قبل از پذیرش پنهان است

        self.client.post(
            reverse("forwarder_panel:land_request_accept", args=[land_request.pk]),
            {"expected_price": "45000000"},
        )
        land_request.refresh_from_db()
        self.assertEqual(land_request.status, LandRequestStatus.ASSIGNED)
        detail = self.client.get(reverse("forwarder_panel:land_request_detail", args=[land_request.pk]))
        self.assertContains(detail, "انبار ۱")

        self.client.force_login(self.customer)
        page = self.client.get(reverse("land_freight:request_detail", args=[land_request.pk]))
        self.assertContains(page, carrier.company_name)

    def test_intracity_form_forces_single_city(self):
        self.client.force_login(self.customer)
        self.client.post(reverse("land_freight:request_create"), {
            "scope": "intracity",
            "origin_province": self.province.pk, "origin_city": self.city_a.pk,
            "pickup_address": "الف", "delivery_address": "ب",
            "pickup_date": (local_today() + timedelta(days=1)).isoformat(),
            "pickup_window": "morning",
            "cargo_type": self.cargo_type.pk, "cargo_description": "اثاثیه", "weight_kg": "300",
            "packaging_type": "other", "vehicle_type": self.nissan.pk,
            "sender_name": "الف", "sender_phone": "09120000000",
            "receiver_name": "ب", "receiver_phone": "09120000001",
            "proposed_price": "8000000",
        })
        land_request = LandFreightRequest.objects.get(customer=self.customer)
        self.assertEqual(land_request.destination_city, self.city_a)

    def test_forwarder_cannot_create_land_request(self):
        carrier = self.make_company("09130000002", service_land_domestic=True, vehicles=[self.nissan])
        self.client.force_login(carrier.admin_user)
        response = self.client.get(reverse("land_freight:request_create"))
        self.assertRedirects(response, reverse("core:home"), fetch_redirect_response=False)


class DeclineTests(LandFreightFixtures):
    def setUp(self):
        self.first = self.make_company("09140000001", service_land_domestic=True, vehicles=[self.nissan])
        self.second = self.make_company("09140000002", service_land_domestic=True, vehicles=[self.nissan])
        self.request = self.make_request()
        publish_request(self.request, self.customer)

    def test_decline_removes_request_only_from_that_inbox(self):
        self.client.force_login(self.first.admin_user)
        response = self.client.post(
            reverse("forwarder_panel:land_request_decline", args=[self.request.pk]),
            {"reason": "کرایه‌ی پیشنهادی کم است"},
        )
        self.assertRedirects(response, reverse("forwarder_panel:land_request_list"), fetch_redirect_response=False)

        dispatch = self.request.dispatches.get(company=self.first)
        self.assertEqual(dispatch.status, DispatchStatus.DECLINED)
        self.assertEqual(dispatch.decline_reason, "کرایه‌ی پیشنهادی کم است")

        # (پیام موفقیت خودش کد درخواست را دارد؛ پس ردیف‌های جدول بررسی می‌شوند نه کل صفحه)
        open_tab = self.client.get(reverse("forwarder_panel:land_request_list"))
        self.assertNotIn(self.request.pk, [r.pk for r in open_tab.context["requests"]])
        self.assertEqual(open_tab.context["counts"]["open"], 0)
        history = self.client.get(reverse("forwarder_panel:land_request_list"), {"tab": "history"})
        self.assertIn(self.request.pk, [r.pk for r in history.context["requests"]])
        self.assertContains(history, "رد شده توسط شما")

        self.client.force_login(self.second.admin_user)
        second_inbox = self.client.get(reverse("forwarder_panel:land_request_list"))
        self.assertIn(self.request.pk, [r.pk for r in second_inbox.context["requests"]])

        # تصمیم رقبا در تاریخچه‌ی درخواست (که مشتری و برنده می‌بینند) ثبت نمی‌شود
        self.assertFalse(self.request.events.filter(note__contains="کرایه‌ی پیشنهادی کم است").exists())

    def test_declined_company_cannot_accept_until_republished(self):
        decline_request(self.request, self.first, "")
        with self.assertRaisesMessage(LandRequestError, "رد کرده"):
            accept_request(self.request.pk, self.first, self.first.admin_user, self.request.proposed_price)

        republish_request(self.request, self.customer, Decimal("70000000"))
        dispatch = self.request.dispatches.get(company=self.first)
        self.assertEqual(dispatch.status, DispatchStatus.SENT)
        self.assertEqual(dispatch.decline_reason, "")
        accept_request(self.request.pk, self.first, self.first.admin_user, Decimal("70000000"))

    def test_cannot_decline_twice_or_after_assignment(self):
        decline_request(self.request, self.first)
        with self.assertRaises(LandRequestError):
            decline_request(self.request, self.first)

        accept_request(self.request.pk, self.second, self.second.admin_user, self.request.proposed_price)
        self.request.refresh_from_db()
        with self.assertRaisesMessage(LandRequestError, "دیگر باز نیست"):
            decline_request(self.request, self.second)


class LandDocumentTests(LandFreightFixtures):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.waybill = DocumentType.objects.create(code="t-waybill", title="بارنامه-آزمون", allowed_extensions="pdf")
        cls.intl_only = DocumentType.objects.create(code="t-intl", title="مدرک-بین‌المللی-آزمون")
        DocumentRule.objects.create(
            title="بارنامه برای برون‌شهری", document_type=cls.waybill,
            requirement_level=DocumentRequirementLevel.TRANSPORT_MODE,
            transport_mode=TransportMode.LAND, land_scope=LandServiceScope.DOMESTIC,
            is_required=True, customer_description="بارنامه‌ی صادره از شرکت",
        )
        DocumentRule.objects.create(
            title="فقط بین‌المللی", document_type=cls.intl_only,
            requirement_level=DocumentRequirementLevel.TRANSPORT_MODE,
            transport_mode=TransportMode.LAND, land_scope=LandServiceScope.INTERNATIONAL,
        )

    def setUp(self):
        self.carrier = self.make_company("09150000001", service_land_domestic=True, vehicles=[self.nissan])
        self.other = self.make_company("09150000002", service_land_domestic=True, vehicles=[self.nissan])
        self.request = self.make_request()
        publish_request(self.request, self.customer)
        self.document = self.request.documents.get(document_type=self.waybill)

    def tearDown(self):
        for doc in LandRequestDocument.objects.exclude(file=""):
            doc.file.delete(save=False)
        super().tearDown()

    def upload_as_customer(self, name="waybill.pdf", content=b"%PDF-1.4"):
        self.client.force_login(self.customer)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("land_freight:document_upload", args=[self.request.pk, self.document.pk]),
                {"file": SimpleUploadedFile(name, content, content_type="application/pdf")},
            )

    def test_rules_by_land_scope_create_the_request_checklist(self):
        types = set(self.request.documents.values_list("document_type__code", flat=True))
        self.assertIn("t-waybill", types)
        self.assertNotIn("t-intl", types)
        self.assertTrue(self.document.is_required)

    def test_customer_uploads_and_only_the_winner_can_view_and_review(self):
        self.upload_as_customer()
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, LandDocumentStatus.UPLOADED)

        page = self.client.get(reverse("land_freight:request_detail", args=[self.request.pk]))
        self.assertContains(page, "بارنامه-آزمون")
        self.assertContains(page, "بارنامه‌ی صادره از شرکت")
        file_url = reverse("land_freight:document_file", args=[self.document.pk])
        self.assertEqual(self.client.get(file_url).status_code, 200)

        # پیش از پذیرش هیچ شرکتی فایل را نمی‌بیند
        self.client.force_login(self.carrier.admin_user)
        self.assertEqual(self.client.get(file_url).status_code, 403)

        accept_request(self.request.pk, self.carrier, self.carrier.admin_user, self.request.proposed_price)
        self.assertEqual(self.client.get(file_url).status_code, 200)
        self.client.force_login(self.other.admin_user)
        self.assertEqual(self.client.get(file_url).status_code, 403)

        review_url = reverse("forwarder_panel:land_document_review", args=[self.request.pk, self.document.pk])
        self.client.post(review_url, {"action": "approve"})  # شرکت غیر برنده
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, LandDocumentStatus.UPLOADED)

        self.client.force_login(self.carrier.admin_user)
        self.client.post(review_url, {"action": "reject", "reason": ""})
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, LandDocumentStatus.UPLOADED)  # رد بدون دلیل پذیرفته نیست

        self.client.post(review_url, {"action": "reject", "reason": "امضا ندارد"})
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, LandDocumentStatus.REJECTED)
        self.assertEqual(self.document.rejection_reason, "امضا ندارد")

        rejected_file = self.document.file.name
        self.upload_as_customer("fixed.pdf")
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, LandDocumentStatus.UPLOADED)
        self.assertEqual(self.document.rejection_reason, "")
        self.assertFalse(self.document.file.storage.exists(rejected_file))  # نسخه‌ی ردشده پاک شد

        self.client.force_login(self.carrier.admin_user)
        self.client.post(review_url, {"action": "approve"})
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, LandDocumentStatus.APPROVED)

    def test_upload_validates_file_type(self):
        self.upload_as_customer("waybill.png", b"\x89PNG")
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, LandDocumentStatus.PENDING_UPLOAD)

    def test_other_customer_cannot_upload_or_view(self):
        stranger = User.objects.create_user(mobile="09150000009", password="Pass12345!", role=User.Role.CUSTOMER)
        self.client.force_login(stranger)
        response = self.client.post(
            reverse("land_freight:document_upload", args=[self.request.pk, self.document.pk]),
            {"file": SimpleUploadedFile("w.pdf", b"%PDF", content_type="application/pdf")},
        )
        self.assertEqual(response.status_code, 404)

    def test_customer_detail_shows_status_steps(self):
        self.client.force_login(self.customer)
        page = self.client.get(reverse("land_freight:request_detail", args=[self.request.pk]))
        self.assertContains(page, "پذیرش توسط شرکت حمل")
        self.assertContains(page, 'aria-current="step"')
