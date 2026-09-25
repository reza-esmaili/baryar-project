from django import forms

from locations.models import City, Country, DestinationCity, Port, Province
from rates.models import CargoType, TransportMode

from .models import (
    InternationalDirection,
    LandCarrierProfile,
    LandFreightRequest,
    LandServiceScope,
    LoaderType,
    VehicleType,
    local_today,
)


class GroupedCityMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} ({obj.province.name})"


class LandCarrierProfileForm(forms.ModelForm):
    """
    حوزه‌ی فعالیت حمل زمینی یک شرکت. قواعد اعتبارسنجی به دسته‌های فعال
    همان شرکت وابسته است، پس company باید پاس داده شود.
    """

    service_cities = GroupedCityMultipleChoiceField(
        queryset=City.objects.none(),
        required=False,
        label="شهرهای تحت پوشش (درون‌شهری)",
        widget=forms.SelectMultiple(attrs={"class": "form-select land-multiselect", "size": 10}),
    )
    service_countries = forms.ModelMultipleChoiceField(
        queryset=Country.objects.none(),
        required=False,
        label="کشورهای تحت پوشش (بین‌المللی)",
        help_text="اگر هیچ کشوری انتخاب نشود، درخواست‌های همه‌ی کشورها برای شما ارسال می‌شود.",
        widget=forms.SelectMultiple(attrs={"class": "form-select land-multiselect", "size": 8}),
    )
    vehicle_types = forms.ModelMultipleChoiceField(
        queryset=VehicleType.objects.none(),
        required=False,
        label="ناوگان در اختیار",
        widget=forms.CheckboxSelectMultiple(),
    )

    class Meta:
        model = LandCarrierProfile
        fields = ["service_cities", "service_countries", "vehicle_types"]

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        self.fields["service_cities"].queryset = (
            City.objects.filter(is_active=True, province__country__code="IRN")
            .select_related("province")
            .order_by("province__name", "name")
        )
        self.fields["service_countries"].queryset = (
            Country.objects.filter(is_active=True).exclude(code="IRN").order_by("name")
        )
        self.fields["vehicle_types"].queryset = VehicleType.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        company = self.company
        if not company:
            return cleaned

        if company.service_land_intracity and not cleaned.get("service_cities"):
            self.add_error("service_cities", "برای حمل درون‌شهری، حداقل یک شهر تحت پوشش انتخاب کنید.")
        if company.offers_land and not cleaned.get("vehicle_types"):
            self.add_error("vehicle_types", "حداقل یک نوع ناوگان انتخاب کنید تا درخواست‌های متناسب برای شما ارسال شود.")
        return cleaned


PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

SELECT = {"class": "form-select"}
INPUT = {"class": "form-control"}
CHECK = {"class": "form-check-input"}


def _iran_cities():
    return City.objects.filter(is_active=True, province__country__code="IRN")


class LandFreightRequestForm(forms.ModelForm):
    """
    فرم ثبت درخواست حمل زمینی. فیلدهای مسیر بسته به نوع حمل معنا دارند:
    درون‌شهری فقط یک شهر، برون‌شهری مبدا و مقصد داخلی، بین‌المللی جهت + یک
    سمت ایرانی + یک سمت خارجی. فیلدهای بی‌ربط به نوع انتخاب‌شده در clean()
    پاک می‌شوند تا داده‌ی ناسازگار ذخیره نشود.
    """

    origin_province = forms.ModelChoiceField(
        queryset=Province.objects.none(), required=False, label="استان مبدا",
        widget=forms.Select(attrs={**SELECT, "data-city-target": "id_origin_city"}),
    )
    destination_province = forms.ModelChoiceField(
        queryset=Province.objects.none(), required=False, label="استان مقصد",
        widget=forms.Select(attrs={**SELECT, "data-city-target": "id_destination_city"}),
    )

    class Meta:
        model = LandFreightRequest
        fields = [
            "scope", "direction",
            "origin_city", "destination_city",
            "foreign_country", "foreign_city", "foreign_city_name", "border_crossing",
            "pickup_address", "delivery_address", "pickup_date", "pickup_window",
            "cargo_type", "cargo_description", "weight_kg", "volume_cbm", "package_count",
            "packaging_type", "cargo_value",
            "is_hazardous", "is_fragile", "needs_refrigeration",
            "vehicle_type", "loader_type",
            "needs_loading_help", "needs_insurance", "needs_customs_clearance",
            "sender_name", "sender_phone", "receiver_name", "receiver_phone",
            "proposed_price", "notes",
        ]
        widgets = {
            "scope": forms.RadioSelect(),
            "direction": forms.RadioSelect(),
            "origin_city": forms.Select(attrs=SELECT),
            "destination_city": forms.Select(attrs=SELECT),
            "foreign_country": forms.Select(attrs=SELECT),
            "foreign_city": forms.Select(attrs=SELECT),
            "foreign_city_name": forms.TextInput(attrs={**INPUT, "placeholder": "اگر شهر در فهرست نیست، نام آن را بنویسید"}),
            "border_crossing": forms.Select(attrs=SELECT),
            "pickup_address": forms.Textarea(attrs={**INPUT, "rows": 2, "placeholder": "خیابان، کوچه، پلاک، واحد"}),
            "delivery_address": forms.Textarea(attrs={**INPUT, "rows": 2, "placeholder": "خیابان، کوچه، پلاک، واحد"}),
            "pickup_date": forms.DateInput(attrs={**INPUT, "type": "date"}),
            "pickup_window": forms.Select(attrs=SELECT),
            "cargo_type": forms.Select(attrs=SELECT),
            "cargo_description": forms.TextInput(attrs={**INPUT, "placeholder": "مثال: ۲۰ کارتن لوازم خانگی"}),
            "weight_kg": forms.NumberInput(attrs={**INPUT, "min": "1", "step": "0.01", "placeholder": "کیلوگرم"}),
            "volume_cbm": forms.NumberInput(attrs={**INPUT, "min": "0", "step": "0.01", "placeholder": "اختیاری"}),
            "package_count": forms.NumberInput(attrs={**INPUT, "min": "1", "placeholder": "اختیاری"}),
            "packaging_type": forms.Select(attrs=SELECT),
            "cargo_value": forms.NumberInput(attrs={**INPUT, "min": "0", "placeholder": "برای بیمه (اختیاری)"}),
            "is_hazardous": forms.CheckboxInput(attrs=CHECK),
            "is_fragile": forms.CheckboxInput(attrs=CHECK),
            "needs_refrigeration": forms.CheckboxInput(attrs=CHECK),
            "vehicle_type": forms.Select(attrs=SELECT),
            "loader_type": forms.Select(attrs=SELECT),
            "needs_loading_help": forms.CheckboxInput(attrs=CHECK),
            "needs_insurance": forms.CheckboxInput(attrs=CHECK),
            "needs_customs_clearance": forms.CheckboxInput(attrs=CHECK),
            "sender_name": forms.TextInput(attrs=INPUT),
            "sender_phone": forms.TextInput(attrs={**INPUT, "inputmode": "tel", "placeholder": "09xxxxxxxxx"}),
            "receiver_name": forms.TextInput(attrs=INPUT),
            "receiver_phone": forms.TextInput(attrs={**INPUT, "inputmode": "tel", "placeholder": "09xxxxxxxxx"}),
            "proposed_price": forms.NumberInput(attrs={**INPUT, "min": "1", "placeholder": "ریال"}),
            "notes": forms.Textarea(attrs={**INPUT, "rows": 3, "placeholder": "هر نکته‌ای که شرکت حمل باید بداند"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        data = self.data

        iran_provinces = Province.objects.filter(is_active=True, country__code="IRN").order_by("name")
        self.fields["origin_province"].queryset = iran_provinces
        self.fields["destination_province"].queryset = iran_provinces

        # بدون گزینه‌ی خالی «---------» که جنگو برای فیلد بدون پیش‌فرض اضافه می‌کند
        self.fields["scope"].choices = LandServiceScope.choices
        self.fields["direction"].required = False
        self.fields["direction"].choices = InternationalDirection.choices

        # شهرها بسته به استان انتخاب‌شده با AJAX پر می‌شوند؛ برای اعتبارسنجی
        # فقط شهرهای همان استان در queryset قرار می‌گیرند.
        self.fields["origin_city"].queryset = self._cities_for(data.get("origin_province"))
        self.fields["destination_city"].queryset = self._cities_for(data.get("destination_province"))

        self.fields["foreign_country"].queryset = (
            Country.objects.filter(is_active=True).exclude(code="IRN").order_by("name")
        )
        country_id = self._int(data.get("foreign_country"))
        self.fields["foreign_city"].queryset = (
            DestinationCity.objects.filter(is_active=True, country_id=country_id).order_by("name")
            if country_id else DestinationCity.objects.none()
        )
        self.fields["border_crossing"].queryset = (
            Port.objects.filter(is_active=True, port_type="land", city__country_id=country_id).order_by("name")
            if country_id else Port.objects.none()
        )

        self.fields["cargo_type"].queryset = CargoType.objects.filter(transport_mode=TransportMode.LAND).order_by("name")
        self.fields["vehicle_type"].queryset = VehicleType.objects.filter(is_active=True)
        self.fields["loader_type"].queryset = LoaderType.objects.filter(is_active=True)
        self.fields["loader_type"].empty_label = "فرقی نمی‌کند"
        self.fields["pickup_date"].widget.attrs["min"] = local_today().isoformat()

        if user and not self.is_bound:
            full_name = f"{user.first_name} {user.last_name}".strip()
            self.initial.setdefault("sender_name", full_name)
            self.initial.setdefault("sender_phone", user.mobile)

    @staticmethod
    def _int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _cities_for(self, province_value):
        province_id = self._int(province_value)
        if not province_id:
            return City.objects.none()
        return _iran_cities().filter(province_id=province_id).order_by("name")

    def _clean_phone(self, field):
        value = (self.cleaned_data.get(field) or "").translate(PERSIAN_DIGITS).replace(" ", "").replace("-", "")
        if value.startswith("+98"):
            value = "0" + value[3:]
        if not value.isdigit() or not 8 <= len(value) <= 11:
            raise forms.ValidationError("شماره تلفن معتبر نیست.")
        return value

    def clean_sender_phone(self):
        return self._clean_phone("sender_phone")

    def clean_receiver_phone(self):
        return self._clean_phone("receiver_phone")

    def clean(self):
        cleaned = super().clean()
        scope = cleaned.get("scope")

        if scope == LandServiceScope.INTRACITY:
            cleaned["destination_city"] = cleaned.get("origin_city")
            self._clear(cleaned, "direction", "foreign_country", "foreign_city", "foreign_city_name",
                        "border_crossing", "needs_customs_clearance")
        elif scope == LandServiceScope.DOMESTIC:
            self._clear(cleaned, "direction", "foreign_country", "foreign_city", "foreign_city_name",
                        "border_crossing", "needs_customs_clearance")
        elif scope == LandServiceScope.INTERNATIONAL:
            direction = cleaned.get("direction")
            if direction == InternationalDirection.EXPORT:
                self._clear(cleaned, "destination_city")
            elif direction == InternationalDirection.IMPORT:
                self._clear(cleaned, "origin_city")
            if cleaned.get("foreign_city"):
                cleaned["foreign_city_name"] = ""

        return cleaned

    @staticmethod
    def _clear(cleaned, *fields):
        empty_values = {"needs_customs_clearance": False, "direction": "", "foreign_city_name": ""}
        for field in fields:
            cleaned[field] = empty_values.get(field)
