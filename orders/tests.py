from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from core.choices import ShippingProcedure
from forwarders.models import ForwarderCompany
from locations.models import City, Country, DestinationCity, Port, Province
from rates.models import CargoType, PricingUnit, Rate, RateTier, TransportMode

from .services import calculate_and_match_rates


class RateMatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        iran = Country.objects.filter(code="IRN").first() or Country.objects.create(name="ایران-آزمون", code="IRN")
        foreign = Country.objects.create(name="مقصد-آزمون", code="TSC")
        province = Province.objects.create(country=iran, name="استان-آزمون-نرخ")
        cls.origin = City.objects.create(province=province, name="بندر-آزمون")
        dest_city = DestinationCity.objects.create(country=foreign, name="شهر-مقصد-آزمون")
        cls.sea_port = Port.objects.create(city=dest_city, name="بندر-مقصد-آزمون", port_type="sea")
        cls.airport = Port.objects.create(city=dest_city, name="فرودگاه-مقصد-آزمون", port_type="air")
        cls.sea_cargo = CargoType.objects.create(name="کالای-دریایی-آزمون", transport_mode=TransportMode.SEA_LCL)
        cls.air_cargo = CargoType.objects.create(name="کالای-هوایی-آزمون", transport_mode=TransportMode.AIR)
        cls.province, cls.foreign, cls.dest_city = province, foreign, dest_city

    def make_company(self, mobile, **overrides):
        user = User.objects.create_user(mobile=mobile, password="Pass12345!", role=User.Role.FORWARDER_ADMIN)
        fields = dict(
            admin_user=user, company_name=f"شرکت {mobile}", company_type="other",
            national_id=mobile, registration_number=mobile,
            ceo_first_name="م", ceo_last_name="ع", ceo_national_code="0012345678",
            phone="02100000000", email=f"{mobile}@example.com", postal_code="1234567890",
            address="آدرس", is_verified=True, is_active=True, service_sea=True, service_air=True,
        )
        fields.update(overrides)
        return ForwarderCompany.objects.create(**fields)

    def make_rate(self, company, mode, port, cargo, tiers):
        rate = Rate.objects.create(
            forwarder=company, transport_mode=mode,
            origin_province=self.province, origin_city=self.origin,
            destination_country=self.foreign, destination_city=self.dest_city, destination_port=port,
            valid_until=timezone.now().date() + timedelta(days=30),
        )
        rate.cargo_types.add(cargo)
        for tier in tiers:
            RateTier.objects.create(rate=rate, **tier)
        return rate

    def quote(self, mode, port, cargo, weight, dims=(), **extra):
        data = {
            "transport_mode": mode, "shipping_procedure": ShippingProcedure.COMMERCIAL,
            "origin_city": self.origin, "destination_port": port, "cargo_type": cargo,
            "actual_weight": Decimal(weight), **extra,
        }
        dimensions = [
            {"length": l, "width": w, "height": h, "quantity": q} for (l, w, h, q) in dims
        ]
        return calculate_and_match_rates(data, dimensions)

    def test_lcl_is_priced_per_w_m_using_volume_when_it_dominates(self):
        company = self.make_company("09140000001")
        self.make_rate(company, TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, [
            dict(pricing_unit=PricingUnit.PER_CBM, price=Decimal("100"), weight_from=0, weight_to=10),
        ])
        # ۲ متر مکعب و ۵۰۰ کیلوگرم → W/M = ۲
        result = self.quote(TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, "500", dims=[(200, 100, 100, 1)])
        self.assertEqual(result["chargeable_unit"], "W/M")
        self.assertEqual(Decimal(result["chargeable_quantity"]), Decimal("2.00"))
        self.assertEqual(Decimal(result["results"][0]["base_shipping_price"]), Decimal("200.00"))

    def test_lcl_uses_weight_in_tonnes_when_heavier_than_volume(self):
        company = self.make_company("09140000002")
        self.make_rate(company, TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, [
            dict(pricing_unit=PricingUnit.PER_CBM, price=Decimal("100"), weight_from=0, weight_to=10),
        ])
        # ۱ متر مکعب و ۳۰۰۰ کیلوگرم → W/M = ۳
        result = self.quote(TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, "3000", dims=[(100, 100, 100, 1)])
        self.assertEqual(Decimal(result["chargeable_quantity"]), Decimal("3.00"))
        self.assertEqual(Decimal(result["results"][0]["base_shipping_price"]), Decimal("300.00"))

    def test_lcl_minimum_is_one_w_m_and_tiers_are_matched_in_w_m(self):
        company = self.make_company("09140000003")
        self.make_rate(company, TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, [
            dict(pricing_unit=PricingUnit.PER_CBM, price=Decimal("150"), weight_from=0, weight_to=5),
            dict(pricing_unit=PricingUnit.PER_CBM, price=Decimal("90"), weight_from=5, weight_to=20),
        ])
        small = self.quote(TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, "100", dims=[(50, 50, 50, 1)])
        self.assertEqual(Decimal(small["chargeable_quantity"]), Decimal("1.00"))
        self.assertEqual(Decimal(small["results"][0]["base_shipping_price"]), Decimal("150.00"))

        large = self.quote(TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, "100", dims=[(200, 200, 200, 1)])
        self.assertEqual(Decimal(large["chargeable_quantity"]), Decimal("8.00"))
        self.assertEqual(Decimal(large["results"][0]["base_shipping_price"]), Decimal("720.00"))

    def test_fcl_is_priced_per_container(self):
        company = self.make_company("09140000004")
        fcl_cargo = CargoType.objects.create(name="کالای-FCL-آزمون", transport_mode=TransportMode.SEA_FCL)
        self.make_rate(company, TransportMode.SEA_FCL, self.sea_port, fcl_cargo, [
            dict(pricing_unit=PricingUnit.PER_CONTAINER, price=Decimal("2000"), container_size="20ft", container_type="dry"),
        ])
        result = self.quote(TransportMode.SEA_FCL, self.sea_port, fcl_cargo, "0",
                            container_size="20ft", container_type="dry", container_count=3)
        self.assertEqual(Decimal(result["results"][0]["base_shipping_price"]), Decimal("6000.00"))

    def test_air_still_uses_6000_volumetric_divisor(self):
        company = self.make_company("09140000005")
        self.make_rate(company, TransportMode.AIR, self.airport, self.air_cargo, [
            dict(pricing_unit=PricingUnit.PER_KG, price=Decimal("10"), weight_from=0, weight_to=1000),
        ])
        # ۶۰۰۰۰ cm³ ÷ ۶۰۰۰ = ۱۰ کیلوگرم حجمی > ۴ کیلوگرم واقعی
        result = self.quote(TransportMode.AIR, self.airport, self.air_cargo, "4", dims=[(60, 50, 20, 1)])
        self.assertEqual(result["chargeable_unit"], "kg")
        self.assertEqual(Decimal(result["chargeable_weight"]), Decimal("10.00"))
        self.assertEqual(Decimal(result["results"][0]["base_shipping_price"]), Decimal("100.00"))

    def test_rates_of_unverified_inactive_or_uncategorized_companies_are_hidden(self):
        tiers = [dict(pricing_unit=PricingUnit.PER_CBM, price=Decimal("100"), weight_from=0, weight_to=10)]
        visible = self.make_company("09140000006")
        self.make_rate(visible, TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, tiers)
        self.make_rate(self.make_company("09140000007", is_verified=False), TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, tiers)
        self.make_rate(self.make_company("09140000008", is_active=False), TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, tiers)
        self.make_rate(self.make_company("09140000009", service_sea=False), TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, tiers)

        result = self.quote(TransportMode.SEA_LCL, self.sea_port, self.sea_cargo, "500", dims=[(100, 100, 100, 1)])
        self.assertEqual([r["company_name"] for r in result["results"]], [visible.company_name])
