from django import forms
from django.db import models, transaction
from django.forms import inlineformset_factory
from locations.models import Country, Province, City

from accounts.models import CompanyType, User
from core.validators import validate_iranian_national_code
from forwarders.models import ForwarderBranch, ForwarderCompany, ForwarderStaff, ForwarderRole
from rates.models import CargoType, Rate, RateTier

class RateForm(forms.ModelForm):
    class Meta:
        model = Rate
        fields = [
            "transport_mode",

            "origin_country",
            "origin_province",
            "origin_city",

            "destination_country",
            "destination_city",
            "destination_port",

            "valid_until",
            "cargo_types",
            "shipping_procedure",

            # بسته‌بندی در دفتر شرکت
            "office_packaging_charge_type",
            "office_packaging_price",

            # بسته‌بندی در محل
            "onsite_packaging_charge_type",
            "onsite_packaging_price",

            # حمل و بسته‌بندی در محل - سرویس مستقل قبلی
            "doorstep_packaging_charge_type",
            "doorstep_packaging_price",

            "add_vat",
        ]

        widgets = {
            "transport_mode": forms.Select(attrs={"class": "form-select"}),

            "origin_country": forms.Select(attrs={"class": "form-select"}),
            "origin_province": forms.Select(attrs={"class": "form-select"}),
            "origin_city": forms.Select(attrs={"class": "form-select"}),

            "destination_country": forms.Select(attrs={"class": "form-select"}),
            "destination_city": forms.Select(attrs={"class": "form-select"}),
            "destination_port": forms.Select(attrs={"class": "form-select"}),

            "valid_until": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "cargo_types": forms.CheckboxSelectMultiple(),
            "shipping_procedure": forms.Select(attrs={"class": "form-select"}),

            "office_packaging_charge_type": forms.Select(attrs={"class": "form-select"}),
            "office_packaging_price": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "step": "0.01",
                }
            ),

            "onsite_packaging_charge_type": forms.Select(attrs={"class": "form-select"}),
            "onsite_packaging_price": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "step": "0.01",
                }
            ),

            "doorstep_packaging_charge_type": forms.Select(attrs={"class": "form-select"}),
            "doorstep_packaging_price": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "step": "0.01",
                }
            ),

            "add_vat": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

        labels = {
            "office_packaging_charge_type": "نوع هزینه بسته‌بندی در دفتر شرکت",
            "office_packaging_price": "مبلغ بسته‌بندی در دفتر شرکت",

            "onsite_packaging_charge_type": "نوع هزینه بسته‌بندی در محل",
            "onsite_packaging_price": "مبلغ بسته‌بندی در محل",

            "doorstep_packaging_charge_type": "نوع هزینه حمل و بسته‌بندی در محل",
            "doorstep_packaging_price": "مبلغ حمل و بسته‌بندی در محل",
        }

        help_texts = {
            "office_packaging_price": "در صورتی که نوع هزینه رایگان یا ارائه نمی‌شود باشد، این مبلغ در محاسبات استفاده نمی‌شود.",
            "onsite_packaging_price": "در صورتی که نوع هزینه رایگان یا ارائه نمی‌شود باشد، این مبلغ در محاسبات استفاده نمی‌شود.",
            "doorstep_packaging_price": "در صورتی که نوع هزینه رایگان یا ارائه نمی‌شود باشد، این مبلغ در محاسبات استفاده نمی‌شود.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["cargo_types"].queryset = CargoType.objects.all()
        self.fields["cargo_types"].widget.choices = [
            (cargo_type.id, cargo_type.name)
            for cargo_type in CargoType.objects.all()
        ]

        iran = Country.objects.filter(code="IRN", is_active=True).first()

        if iran:
            self.fields["origin_country"].queryset = Country.objects.filter(id=iran.id)
            self.fields["origin_country"].initial = iran.id

            self.fields["origin_province"].queryset = Province.objects.filter(
                country=iran,
                is_active=True
            ).order_by("name")
        else:
            self.fields["origin_country"].queryset = Country.objects.none()
            self.fields["origin_province"].queryset = Province.objects.none()

        self.fields["origin_city"].queryset = City.objects.none()

        if "origin_province" in self.data:
            try:
                province_id = int(self.data.get("origin_province"))
                self.fields["origin_city"].queryset = City.objects.filter(
                    province_id=province_id,
                    is_active=True
                ).order_by("name")
            except (ValueError, TypeError):
                pass

        elif self.instance.pk and self.instance.origin_province:
            self.fields["origin_city"].queryset = City.objects.filter(
                province=self.instance.origin_province,
                is_active=True
            ).order_by("name")

    def clean(self):
        cleaned_data = super().clean()

        office_type = cleaned_data.get("office_packaging_charge_type")
        office_price = cleaned_data.get("office_packaging_price")

        onsite_type = cleaned_data.get("onsite_packaging_charge_type")
        onsite_price = cleaned_data.get("onsite_packaging_price")

        doorstep_type = cleaned_data.get("doorstep_packaging_charge_type")
        doorstep_price = cleaned_data.get("doorstep_packaging_price")

        fixed_or_per_kg_types = ["fixed", "per_kg"]

        if office_type in fixed_or_per_kg_types and (office_price is None or office_price <= 0):
            self.add_error(
                "office_packaging_price",
                "برای بسته‌بندی در دفتر شرکت، در حالت هزینه ثابت یا به ازای هر کیلوگرم باید مبلغ وارد شود."
            )

        if onsite_type in fixed_or_per_kg_types and (onsite_price is None or onsite_price <= 0):
            self.add_error(
                "onsite_packaging_price",
                "برای بسته‌بندی در محل، در حالت هزینه ثابت یا به ازای هر کیلوگرم باید مبلغ وارد شود."
            )

        if doorstep_type in fixed_or_per_kg_types and (doorstep_price is None or doorstep_price <= 0):
            self.add_error(
                "doorstep_packaging_price",
                "برای حمل و بسته‌بندی در محل، در حالت هزینه ثابت یا به ازای هر کیلوگرم باید مبلغ وارد شود."
            )

        return cleaned_data

 
class RateTierForm(forms.ModelForm):
    class Meta:
        model = RateTier
        fields = [
            "weight_from",
            "weight_to",
            "pricing_unit",
            "price",
            "container_size",
            "container_type",
        ]
        widgets = {
            "weight_from": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "از وزن (KG)"}
            ),
            "weight_to": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "تا وزن (KG)"}
            ),
            "pricing_unit": forms.Select(attrs={"class": "form-select"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "placeholder": "مبلغ"}),
            "container_size": forms.Select(attrs={"class": "form-select"}),
            "container_type": forms.Select(attrs={"class": "form-select"}),
        }


RateTierFormSet = inlineformset_factory(
    Rate,
    RateTier,
    form=RateTierForm,
    extra=1,
    can_delete=True,
)


class BranchForm(forms.ModelForm):
    class Meta:
        model = ForwarderBranch
        fields = [
            "name",
            "representative_first_name",
            "representative_last_name",
            "representative_mobile",
            "province",
            "city",
            "address",
            "is_active",
        ]
        labels = {
            "name": "نام شعبه",
            "representative_first_name": "نام مدیر / نماینده",
            "representative_last_name": "نام خانوادگی",
            "representative_mobile": "شماره موبایل",
            "province": "استان",
            "city": "شهر",
            "address": "آدرس کامل",
            "is_active": "شعبه فعال است؟",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: شعبه تهران"}
            ),
            "representative_first_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام"}
            ),
            "representative_last_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام خانوادگی"}
            ),
            "representative_mobile": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "0912..."}
            ),
            "province": forms.Select(attrs={"class": "form-select"}),
            "city": forms.Select(attrs={"class": "form-select"}),
            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "آدرس دقیق را وارد کنید...",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "form-check-input", "role": "switch"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["city"].queryset = City.objects.none()

        if "province" in self.data:
            try:
                province_id = int(self.data.get("province"))
                self.fields["city"].queryset = City.objects.filter(
                    province_id=province_id
                ).order_by("name")
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.province:
            self.fields["city"].queryset = self.instance.province.cities.order_by("name")

    def clean_representative_mobile(self):
        mobile = self.cleaned_data["representative_mobile"]
        qs = User.objects.filter(mobile=mobile)
        if self.instance.pk and self.instance.branch_user_id:
            qs = qs.exclude(pk=self.instance.branch_user_id)
        if qs.exists():
            raise forms.ValidationError("این شماره موبایل قبلاً ثبت شده است.")
        return mobile

    @transaction.atomic
    def save(self, forwarder_company, commit=True):
        branch = super().save(commit=False)
        branch.company = forwarder_company

        if not branch.pk:
            user = User.objects.create_user(
                mobile=self.cleaned_data["representative_mobile"],
                first_name=self.cleaned_data["representative_first_name"],
                last_name=self.cleaned_data["representative_last_name"],
                password=self.cleaned_data["representative_mobile"],
            )
            branch.branch_user = user
        else:
            user = branch.branch_user
            user.first_name = self.cleaned_data["representative_first_name"]
            user.last_name = self.cleaned_data["representative_last_name"]
            user.mobile = self.cleaned_data["representative_mobile"]
            user.save()

        if commit:
            branch.save()

        return branch


class StaffForm(forms.Form):
    first_name = forms.CharField(max_length=100, label="نام")
    last_name = forms.CharField(max_length=100, label="نام خانوادگی")
    national_code = forms.CharField(max_length=10, label="کد ملی")
    mobile = forms.CharField(max_length=15, label="شماره موبایل")
    role = forms.ModelChoiceField(
        queryset=ForwarderRole.objects.none(),
        label="نقش",
        empty_label="-- انتخاب نقش --",
        required=False,
    )
    is_active = forms.BooleanField(
        label="حساب کاربری فعال باشد",
        required=False,
        initial=True,
    )

    def __init__(self, *args, forwarder_company=None, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._staff_instance = instance
        if forwarder_company:
            self.fields['role'].queryset = ForwarderRole.objects.filter(company=forwarder_company)
        if instance:
            self.fields['first_name'].initial = instance.user.first_name
            self.fields['last_name'].initial = instance.user.last_name
            self.fields['national_code'].initial = instance.national_code
            self.fields['mobile'].initial = instance.user.mobile
            self.fields['role'].initial = instance.role
            self.fields['is_active'].initial = instance.is_active
            self.fields['mobile'].widget.attrs['readonly'] = True
        else:
            # در حالت ایجاد فیلد is_active نیازی به نمایش ندارد
            self.fields['is_active'].widget = forms.HiddenInput()
            self.fields['is_active'].initial = True

    def clean_mobile(self):
        mobile = self.cleaned_data['mobile']
        qs = User.objects.filter(mobile=mobile)
        if self._staff_instance:
            qs = qs.exclude(pk=self._staff_instance.user.pk)
        if qs.exists():
            raise forms.ValidationError("این شماره موبایل قبلاً ثبت شده است.")
        return mobile

    def clean_national_code(self):
        nc = self.cleaned_data['national_code'].strip()
        # اعتبارسنجی الگوریتم کد ملی ایرانی
        from django.core.exceptions import ValidationError as DjValidationError
        try:
            validate_iranian_national_code(nc)
        except DjValidationError as e:
            raise forms.ValidationError(e.message)
        # بررسی تکراری نبودن
        qs = ForwarderStaff.objects.filter(national_code=nc)
        if self._staff_instance:
            qs = qs.exclude(pk=self._staff_instance.pk)
        if qs.exists():
            raise forms.ValidationError("این کد ملی قبلاً برای کارمند دیگری ثبت شده است.")
        return nc

    @transaction.atomic
    def save(self, forwarder_company):
        instance = self._staff_instance
        is_active = self.cleaned_data.get('is_active', True)
        if instance is None:
            user = User.objects.create_user(
                mobile=self.cleaned_data['mobile'],
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                password=self.cleaned_data['national_code'],
                role=User.Role.FORWARDER_EXPERT,
                must_change_password=True,
            )
            staff = ForwarderStaff(company=forwarder_company, user=user)
        else:
            instance.user.first_name = self.cleaned_data['first_name']
            instance.user.last_name = self.cleaned_data['last_name']
            instance.user.is_active = is_active
            instance.user.save(update_fields=['first_name', 'last_name', 'is_active'])
            staff = instance

        staff.national_code = self.cleaned_data['national_code']
        staff.role = self.cleaned_data.get('role')
        staff.is_active = is_active
        staff.save()
        return staff


class ForwarderDocumentsForm(forms.Form):
    class ApplicantRole(models.TextChoices):
        CEO = "ceo", "مدیرعامل"
        REPRESENTATIVE = "representative", "نماینده شرکت"

    applicant_role = forms.ChoiceField(
        label="نقش فرد ثبت‌نام‌کننده",
        choices=ApplicantRole.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    company_name = forms.CharField(
        label="نام شرکت",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    company_type = forms.ChoiceField(
        label="نوع شرکت",
        choices=CompanyType.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    national_id = forms.CharField(
        label="شناسه ملی شرکت",
        max_length=11,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    registration_number = forms.CharField(
        label="شماره ثبت",
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    phone = forms.CharField(
        label="تلفن شرکت",
        max_length=15,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    email = forms.EmailField(
        label="ایمیل شرکت",
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )

    postal_code = forms.CharField(
        label="کد پستی",
        max_length=10,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    address = forms.CharField(
        label="آدرس شرکت",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )

    ceo_first_name = forms.CharField(
        label="نام مدیرعامل",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    ceo_last_name = forms.CharField(
        label="نام خانوادگی مدیرعامل",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    ceo_mobile = forms.CharField(
        label="موبایل مدیرعامل",
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    ceo_national_code = forms.CharField(
        label="کد ملی مدیرعامل",
        max_length=10,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    articles_of_association = forms.FileField(
        label="اساسنامه",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )

    establishment_notice = forms.FileField(
        label="آگهی تاسیس",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )

    latest_changes = forms.FileField(
        label="آخرین تغییرات",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )

    ceo_national_card = forms.FileField(
        label="کارت ملی مدیرعامل",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, user=None, company=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.company = company

        if company:
            self.fields["company_name"].initial = company.company_name
            self.fields["company_type"].initial = company.company_type
            self.fields["national_id"].initial = company.national_id
            self.fields["registration_number"].initial = company.registration_number
            self.fields["phone"].initial = company.phone
            self.fields["email"].initial = company.email
            self.fields["postal_code"].initial = company.postal_code
            self.fields["address"].initial = company.address
            self.fields["ceo_first_name"].initial = company.ceo_first_name
            self.fields["ceo_last_name"].initial = company.ceo_last_name
            if hasattr(company, "ceo_mobile"):
                self.fields["ceo_mobile"].initial = company.ceo_mobile

            self.fields["ceo_national_code"].initial = company.ceo_national_code

            self.fields["articles_of_association"].required = False
            self.fields["establishment_notice"].required = False
            self.fields["latest_changes"].required = False
            self.fields["ceo_national_card"].required = False

    def clean_national_id(self):
        national_id = self.cleaned_data.get("national_id")

        if not national_id:
            return national_id

        if not national_id.isdigit() or len(national_id) != 11:
            raise forms.ValidationError("شناسه ملی باید ۱۱ رقم باشد.")

        queryset = ForwarderCompany.objects.filter(national_id=national_id)

        if self.company:
            queryset = queryset.exclude(pk=self.company.pk)

        if queryset.exists():
            raise forms.ValidationError("این شناسه ملی قبلاً ثبت شده است.")

        return national_id

    def clean_postal_code(self):
        postal_code = self.cleaned_data.get("postal_code")

        if not postal_code:
            return postal_code

        if not postal_code.isdigit() or len(postal_code) != 10:
            raise forms.ValidationError("کد پستی باید ۱۰ رقم باشد.")

        return postal_code

    def clean_ceo_national_code(self):
        national_code = self.cleaned_data.get("ceo_national_code")

        if national_code and (
            not national_code.isdigit() or len(national_code) != 10
        ):
            raise forms.ValidationError("کد ملی باید ۱۰ رقم باشد.")

        return national_code

    def clean_ceo_mobile(self):
        mobile = self.cleaned_data.get("ceo_mobile")

        if mobile and not mobile.isdigit():
            raise forms.ValidationError("شماره موبایل فقط باید شامل عدد باشد.")

        return mobile

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("applicant_role")

        if role == self.ApplicantRole.REPRESENTATIVE:
            required_fields = [
                "ceo_first_name",
                "ceo_last_name",
                "ceo_mobile",
                "ceo_national_code",
            ]

            for field in required_fields:
                if not cleaned_data.get(field):
                    self.add_error(field, "این فیلد الزامی است.")

        return cleaned_data
