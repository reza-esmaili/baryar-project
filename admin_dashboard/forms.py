# admin_dashboard/forms.py

from django import forms

from accounts.models import User, OTPCode
from core.models import SmsProviderConfig, SmsEvent
from core.services.notifications.events import get_event_params
from core.services.notifications.sms import validate_custom_text_params
from documents.models import DocumentType, AdditionalDocumentRequest
from forwarders.models import ForwarderRole, ForwarderCompany
from locations.models import Country, Province, City, DestinationCity, Port
from orders.models import CargoRequest
from rates.models import CargoType, CargoSubCategory, CargoSubCategoryChild, Rate
from support.models import SupportDepartment, TicketTopic, SupportAgent

# فرم‌های پیچیده (کسکید کردن dropdown، اعتبارسنجی چندمرحله‌ای) از همان محلی که
# قبلاً برای پنل فورواردر/ادمین جنگو نوشته شده بودند دوباره استفاده می‌شوند تا
# منطق تکرار نشود.
from panel.forms import RateForm, RateTierForm, RateTierFormSet, BranchForm, StaffForm  # noqa: F401
from documents.admin import DocumentRuleAdminForm  # noqa: F401


FORM_CONTROL_ATTRS = {"class": "form-control"}
FORM_SELECT_ATTRS = {"class": "form-select"}
FORM_CHECK_ATTRS = {"class": "form-check-input"}


class CountryForm(forms.ModelForm):
    class Meta:
        model = Country
        fields = ["name", "code", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "code": forms.TextInput(attrs={**FORM_CONTROL_ATTRS, "maxlength": 3, "placeholder": "IRN"}),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }


class ProvinceForm(forms.ModelForm):
    class Meta:
        model = Province
        fields = ["country", "name", "is_active"]
        widgets = {
            "country": forms.Select(attrs=FORM_SELECT_ATTRS),
            "name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }


class CityForm(forms.ModelForm):
    class Meta:
        model = City
        fields = ["province", "name", "is_active"]
        widgets = {
            "province": forms.Select(attrs=FORM_SELECT_ATTRS),
            "name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }


class DestinationCityForm(forms.ModelForm):
    class Meta:
        model = DestinationCity
        fields = ["country", "name", "is_active"]
        widgets = {
            "country": forms.Select(attrs=FORM_SELECT_ATTRS),
            "name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }


class PortForm(forms.ModelForm):
    class Meta:
        model = Port
        fields = ["city", "name", "port_type", "code", "is_active"]
        widgets = {
            "city": forms.Select(attrs=FORM_SELECT_ATTRS),
            "name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "port_type": forms.Select(attrs=FORM_SELECT_ATTRS),
            "code": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }


class CargoTypeForm(forms.ModelForm):
    class Meta:
        model = CargoType
        fields = ["name", "transport_mode"]
        widgets = {
            "name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "transport_mode": forms.Select(attrs=FORM_SELECT_ATTRS),
        }


class CargoSubCategoryForm(forms.ModelForm):
    class Meta:
        model = CargoSubCategory
        fields = ["category", "name", "description"]
        widgets = {
            "category": forms.Select(attrs=FORM_SELECT_ATTRS),
            "name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "description": forms.Textarea(attrs={**FORM_CONTROL_ATTRS, "rows": 3}),
        }


class CargoSubCategoryChildForm(forms.ModelForm):
    class Meta:
        model = CargoSubCategoryChild
        fields = ["subcategory", "name", "description"]
        widgets = {
            "subcategory": forms.Select(attrs=FORM_SELECT_ATTRS),
            "name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "description": forms.Textarea(attrs={**FORM_CONTROL_ATTRS, "rows": 3}),
        }


class DocumentTypeForm(forms.ModelForm):
    class Meta:
        model = DocumentType
        fields = ["title", "code", "description", "allowed_extensions", "max_file_size_mb", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "code": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "description": forms.Textarea(attrs={**FORM_CONTROL_ATTRS, "rows": 3}),
            "allowed_extensions": forms.TextInput(attrs={**FORM_CONTROL_ATTRS, "placeholder": "pdf,jpg,jpeg,png"}),
            "max_file_size_mb": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }


class SupportDepartmentForm(forms.ModelForm):
    class Meta:
        model = SupportDepartment
        fields = ["name", "panel_type", "is_active", "sla_response_minutes", "sla_resolve_minutes"]
        widgets = {
            "name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "panel_type": forms.Select(attrs=FORM_SELECT_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
            "sla_response_minutes": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "sla_resolve_minutes": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
        }


class TicketTopicForm(forms.ModelForm):
    class Meta:
        model = TicketTopic
        fields = ["department", "title", "is_active"]
        widgets = {
            "department": forms.Select(attrs=FORM_SELECT_ATTRS),
            "title": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }


class SupportAgentForm(forms.ModelForm):
    class Meta:
        model = SupportAgent
        fields = ["user", "departments", "is_supervisor", "is_active"]
        widgets = {
            "user": forms.Select(attrs=FORM_SELECT_ATTRS),
            "departments": forms.CheckboxSelectMultiple(),
            "is_supervisor": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # فقط کاربرانی که هنوز پروفایل پشتیبان ندارند (یا خودِ کاربر جاری فرم)
        used_ids = SupportAgent.objects.exclude(pk=self.instance.pk).values_list("user_id", flat=True)
        self.fields["user"].queryset = User.objects.exclude(id__in=used_ids).order_by("first_name")


class ForwarderRoleForm(forms.ModelForm):
    class Meta:
        model = ForwarderRole
        fields = "__all__"
        widgets = {
            "company": forms.Select(attrs=FORM_SELECT_ATTRS),
            "name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update(FORM_CHECK_ATTRS)


class AdminRateForm(RateForm):
    """
    همان RateForm پنل فورواردر، به‌علاوه فیلدهای forwarder/branch/is_active که
    در پنل فورواردر (چون خودِ فورواردر رتبه‌اش را برای شرکت خودش می‌سازد)
    نیازی نبود، ولی برای ادمین که نرخ همه‌ی شرکت‌ها را می‌بیند لازم است.
    """

    class Meta(RateForm.Meta):
        fields = RateForm.Meta.fields + ["forwarder", "branch", "is_active"]
        widgets = {
            **RateForm.Meta.widgets,
            "forwarder": forms.Select(attrs=FORM_SELECT_ATTRS),
            "branch": forms.Select(attrs=FORM_SELECT_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }


class UserForm(forms.ModelForm):
    """
    برای هم ایجاد و هم ویرایش کاربر استفاده می‌شود. یکتا بودن mobile/email با
    اعتبارسنجی خودکار ModelForm انجام می‌شود (که هنگام ویرایش خودِ کاربر را از
    بررسی استثنا می‌کند)؛ فقط لازم است شماره موبایل قبل از آن نرمال شود تا
    فرمت‌های مختلف یک شماره به‌عنوان تکراری تشخیص داده نشوند.
    """

    class Meta:
        model = User
        fields = ["mobile", "first_name", "last_name", "email", "role", "is_active", "is_staff"]
        widgets = {
            "mobile": forms.TextInput(attrs={**FORM_CONTROL_ATTRS, "placeholder": "09xxxxxxxxx"}),
            "first_name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "last_name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "email": forms.EmailInput(attrs=FORM_CONTROL_ATTRS),
            "role": forms.Select(attrs=FORM_SELECT_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
            "is_staff": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }
        labels = {
            "mobile": "شماره موبایل",
            "first_name": "نام",
            "last_name": "نام خانوادگی",
            "email": "ایمیل",
            "role": "نقش",
            "is_active": "فعال",
            "is_staff": "دسترسی به داشبورد مدیریت (Staff)",
        }

    def clean_mobile(self):
        mobile = self.cleaned_data.get("mobile")
        if mobile:
            mobile = OTPCode.normalize_mobile(mobile)
        return mobile


class ForwarderCompanyForm(forms.ModelForm):
    class Meta:
        model = ForwarderCompany
        fields = [
            "company_name", "company_type", "national_id", "registration_number",
            "ceo_first_name", "ceo_last_name", "ceo_national_code",
            "phone", "email", "postal_code", "address",
            "logo", "description", "website", "instagram", "linkedin",
            "is_verified", "is_active",
        ]
        widgets = {
            "company_name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "company_type": forms.Select(attrs=FORM_SELECT_ATTRS),
            "national_id": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "registration_number": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "ceo_first_name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "ceo_last_name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "ceo_national_code": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "phone": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "email": forms.EmailInput(attrs=FORM_CONTROL_ATTRS),
            "postal_code": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "address": forms.Textarea(attrs={**FORM_CONTROL_ATTRS, "rows": 3}),
            "description": forms.Textarea(attrs={**FORM_CONTROL_ATTRS, "rows": 3}),
            "website": forms.URLInput(attrs=FORM_CONTROL_ATTRS),
            "instagram": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "linkedin": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "is_verified": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }
        labels = {
            "company_type": "نوع شرکت",
            "national_id": "شناسه ملی شرکت",
            "registration_number": "شماره ثبت",
            "ceo_first_name": "نام مدیرعامل",
            "ceo_last_name": "نام خانوادگی مدیرعامل",
            "ceo_national_code": "کد ملی مدیرعامل",
            "phone": "تلفن شرکت",
            "email": "ایمیل شرکت",
            "postal_code": "کد پستی",
            "address": "آدرس",
            "logo": "لوگو",
            "description": "توضیحات",
            "website": "وب‌سایت",
            "instagram": "اینستاگرام",
            "linkedin": "لینکدین",
            "is_verified": "تایید شده",
            "is_active": "فعال",
        }

    def clean_national_id(self):
        value = self.cleaned_data.get("national_id")
        if value and (not value.isdigit() or len(value) != 11):
            raise forms.ValidationError("شناسه ملی باید ۱۱ رقم باشد.")
        return value

    def clean_postal_code(self):
        value = self.cleaned_data.get("postal_code")
        if value and (not value.isdigit() or len(value) != 10):
            raise forms.ValidationError("کد پستی باید ۱۰ رقم باشد.")
        return value

    def clean_ceo_national_code(self):
        value = self.cleaned_data.get("ceo_national_code")
        if value and (not value.isdigit() or len(value) != 10):
            raise forms.ValidationError("کد ملی باید ۱۰ رقم باشد.")
        return value


class ForwarderAdminUserForm(forms.ModelForm):
    """
    فقط برای ایجاد شرکت جدید استفاده می‌شود: چون ForwarderCompany.admin_user
    یک OneToOne اجباری است، ساخت شرکت از سمت ادمین یعنی هم‌زمان باید یک
    کاربر «ادمین فورواردر» هم ساخته شود (مشابه الگوی BranchForm/StaffForm در
    panel/forms.py: رمز موقت = شماره موبایل + اجبار به تغییر رمز در ورود اول).
    """

    class Meta:
        model = User
        fields = ["mobile", "first_name", "last_name", "email"]
        widgets = {
            "mobile": forms.TextInput(attrs={**FORM_CONTROL_ATTRS, "placeholder": "09xxxxxxxxx"}),
            "first_name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "last_name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "email": forms.EmailInput(attrs=FORM_CONTROL_ATTRS),
        }
        labels = {
            "mobile": "شماره موبایل",
            "first_name": "نام",
            "last_name": "نام خانوادگی",
            "email": "ایمیل",
        }

    def clean_mobile(self):
        mobile = self.cleaned_data.get("mobile")
        if not mobile:
            return mobile
        normalized = OTPCode.normalize_mobile(mobile)
        if User.objects.filter(mobile=normalized).exists():
            raise forms.ValidationError("این شماره موبایل قبلاً برای یک کاربر دیگر ثبت شده است.")
        return normalized

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("این ایمیل قبلاً برای یک کاربر دیگر ثبت شده است.")
        return email


class OrderForm(forms.ModelForm):
    """
    ویرایش تمام فیلدهای درخواست حمل، معادل صفحه ویرایش CargoRequest در ادمین
    جنگو (که ModelAdmin سفارشی‌ای ندارد و همه فیلدها را نمایش می‌دهد). فیلد
    «مشتری» عمداً در این فرم نیست چون تغییر صاحب سفارش عملاً بی‌معناست؛ در
    قالب به‌صورت غیرقابل‌ویرایش نمایش داده می‌شود (مشابه admin_user در
    ForwarderCompanyForm).
    """

    class Meta:
        model = CargoRequest
        fields = [
            "status",
            "origin_country", "origin_province", "origin_city",
            "destination_port", "transport_mode", "shipping_procedure",
            "cargo_type", "cargo_subcategories", "other_cargo_details",
            "actual_weight", "chargeable_weight",
            "container_size", "container_type", "container_count",
            "needs_office_packaging", "needs_onsite_packaging", "needs_doorstep_packaging",
            "selected_rate",
            "base_shipping_price", "office_packaging_price", "onsite_packaging_price",
            "doorstep_packaging_price", "vat_amount", "price_subtotal", "final_price",
            "sender_name", "sender_national_id", "sender_phone",
            "sender_province", "sender_city", "sender_address",
        ]
        widgets = {
            "status": forms.Select(attrs=FORM_SELECT_ATTRS),
            "origin_country": forms.Select(attrs=FORM_SELECT_ATTRS),
            "origin_province": forms.Select(attrs=FORM_SELECT_ATTRS),
            "origin_city": forms.Select(attrs=FORM_SELECT_ATTRS),
            "destination_port": forms.Select(attrs=FORM_SELECT_ATTRS),
            "transport_mode": forms.Select(attrs=FORM_SELECT_ATTRS),
            "shipping_procedure": forms.Select(attrs=FORM_SELECT_ATTRS),
            "cargo_type": forms.Select(attrs=FORM_SELECT_ATTRS),
            "cargo_subcategories": forms.SelectMultiple(attrs={**FORM_SELECT_ATTRS, "size": 6}),
            "other_cargo_details": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "actual_weight": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "chargeable_weight": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "container_size": forms.Select(attrs=FORM_SELECT_ATTRS),
            "container_type": forms.Select(attrs=FORM_SELECT_ATTRS),
            "container_count": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "needs_office_packaging": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
            "needs_onsite_packaging": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
            "needs_doorstep_packaging": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
            "selected_rate": forms.Select(attrs=FORM_SELECT_ATTRS),
            "base_shipping_price": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "office_packaging_price": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "onsite_packaging_price": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "doorstep_packaging_price": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "vat_amount": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "price_subtotal": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "final_price": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
            "sender_name": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "sender_national_id": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "sender_phone": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "sender_province": forms.Select(attrs=FORM_SELECT_ATTRS),
            "sender_city": forms.Select(attrs=FORM_SELECT_ATTRS),
            "sender_address": forms.Textarea(attrs={**FORM_CONTROL_ATTRS, "rows": 2}),
        }


class AdditionalDocumentRequestForm(forms.ModelForm):
    class Meta:
        model = AdditionalDocumentRequest
        fields = ["order", "title", "description", "document_type", "custom_document_title", "expires_at"]
        widgets = {
            "order": forms.Select(attrs=FORM_SELECT_ATTRS),
            "title": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "description": forms.Textarea(attrs={**FORM_CONTROL_ATTRS, "rows": 3}),
            "document_type": forms.Select(attrs=FORM_SELECT_ATTRS),
            "custom_document_title": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "expires_at": forms.DateInput(attrs={**FORM_CONTROL_ATTRS, "type": "date"}),
        }


class SmsProviderConfigForm(forms.ModelForm):
    class Meta:
        model = SmsProviderConfig
        fields = ["provider_type", "api_key", "default_line_number", "is_active"]
        widgets = {
            "provider_type": forms.Select(attrs=FORM_SELECT_ATTRS),
            "api_key": forms.TextInput(attrs={**FORM_CONTROL_ATTRS, "autocomplete": "off"}),
            "default_line_number": forms.TextInput(attrs=FORM_CONTROL_ATTRS),
            "is_active": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
        }


class SmsEventForm(forms.ModelForm):
    """
    فرم ویرایش یک رویداد پیامکی. فیلدهای نگاشت پارامتر (parameter_mapping)
    پویا و بر اساس پارامترهای ثبت‌شده همان رویداد در
    core/services/notifications/events.py ساخته می‌شوند — نه یک فرم‌ست، چون
    نام پارامترهای هر رویداد در کد ثابت است و فقط نگاشت به نام قالب sms.ir
    باید توسط ادمین وارد شود.
    """

    class Meta:
        model = SmsEvent
        fields = ["is_enabled", "send_mode", "custom_text", "template_id"]
        widgets = {
            "is_enabled": forms.CheckboxInput(attrs=FORM_CHECK_ATTRS),
            "send_mode": forms.Select(attrs=FORM_SELECT_ATTRS),
            "custom_text": forms.Textarea(attrs={**FORM_CONTROL_ATTRS, "rows": 3}),
            "template_id": forms.NumberInput(attrs=FORM_CONTROL_ATTRS),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.param_keys = list(get_event_params(self.instance.code).keys())
        existing_mapping = self.instance.parameter_mapping or {}

        for key in self.param_keys:
            self.fields[f"param_map__{key}"] = forms.CharField(
                required=False,
                label=key,
                initial=existing_mapping.get(key, ""),
                widget=forms.TextInput(attrs={**FORM_CONTROL_ATTRS, "placeholder": "نام این پارامتر در قالب sms.ir"}),
            )

    def clean_custom_text(self):
        text = self.cleaned_data.get("custom_text", "")
        send_mode = self.data.get("send_mode")
        if send_mode == SmsEvent.SendMode.CUSTOM and text:
            unknown = validate_custom_text_params(text, self.param_keys)
            if unknown:
                raise forms.ValidationError(
                    f"پارامتر(های) نامعتبر در متن: {', '.join(unknown)}. "
                    f"پارامترهای مجاز: {', '.join(self.param_keys)}"
                )
        return text

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("send_mode") == SmsEvent.SendMode.TEMPLATE and not cleaned.get("template_id"):
            self.add_error("template_id", "برای ارسال با قالب sms.ir، شناسه قالب الزامی است.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.parameter_mapping = {
            key: self.cleaned_data.get(f"param_map__{key}", "").strip()
            for key in self.param_keys
            if self.cleaned_data.get(f"param_map__{key}", "").strip()
        }
        if commit:
            instance.save()
        return instance
