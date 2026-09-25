from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from forwarders.models import ForwarderCompany
from locations.models import City, Country, DestinationCity, Port, Province
from orders.models import CustomerNotification, ForwarderNotification
from rates.models import CargoType, TransportMode

from .models import (
    DispatchStatus,
    InternationalDirection,
    LandCarrierProfile,
    LandFreightRequest,
    LandRequestStatus,
    LandServiceScope,
    VehicleType,
    local_today,
)
from .services import (
    LandRequestError,
    accept_request,
    cancel_request,
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
