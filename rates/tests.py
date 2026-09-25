from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from forwarders.models import ForwarderCompany
from locations.models import City, Country, DestinationCity, Port, Province

from .models import Rate, TransportMode


class RateApiAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        iran = Country.objects.filter(code="IRN").first() or Country.objects.create(name="ایران-آزمون", code="IRN")
        foreign = Country.objects.create(name="مقصد-آزمون-api", code="TSD")
        province = Province.objects.create(country=iran, name="استان-آزمون-api")
        city = City.objects.create(province=province, name="شهر-آزمون-api")
        dest_city = DestinationCity.objects.create(country=foreign, name="شهر-مقصد-api")
        airport = Port.objects.create(city=dest_city, name="فرودگاه-api", port_type="air")

        cls.owner = cls._company("09150000001")
        cls.other = cls._company("09150000002")
        for company in (cls.owner, cls.other):
            Rate.objects.create(
                forwarder=company, transport_mode=TransportMode.AIR,
                origin_province=province, origin_city=city,
                destination_country=foreign, destination_city=dest_city, destination_port=airport,
                valid_until=timezone.now().date() + timedelta(days=10),
            )
        cls.customer = User.objects.create_user(mobile="09150000009", password="Pass12345!", role=User.Role.CUSTOMER)

    @staticmethod
    def _company(mobile):
        user = User.objects.create_user(mobile=mobile, password="Pass12345!", role=User.Role.FORWARDER_ADMIN)
        return ForwarderCompany.objects.create(
            admin_user=user, company_name=f"شرکت {mobile}", company_type="other",
            national_id=mobile, registration_number=mobile,
            ceo_first_name="م", ceo_last_name="ع", ceo_national_code="0012345678",
            phone="02100000000", email=f"{mobile}@example.com", postal_code="1234567890",
            address="آدرس", is_verified=True, is_active=True, service_air=True,
        )

    def setUp(self):
        self.client = APIClient()

    def test_customer_cannot_access_rates_api(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get("/api/v1/rates/rates/").status_code, 403)

    def test_forwarder_sees_and_can_delete_only_own_rates(self):
        self.client.force_authenticate(self.owner.admin_user)
        response = self.client.get("/api/v1/rates/rates/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        rows = payload["results"] if isinstance(payload, dict) else payload
        self.assertEqual({row["forwarder"] for row in rows}, {self.owner.id})

        other_rate = Rate.objects.get(forwarder=self.other)
        self.assertEqual(self.client.delete(f"/api/v1/rates/rates/{other_rate.id}/").status_code, 404)
        self.assertTrue(Rate.objects.filter(pk=other_rate.pk).exists())
