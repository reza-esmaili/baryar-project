from django import forms
from django.forms import inlineformset_factory
from .models import CargoRequest, CargoDimension
from locations.models import Province, City, Country, DestinationCity, Port
from rates.models import ContainerSize, ContainerType, CargoSubCategory
from core.validators import validate_iranian_national_code

class CargoRequestForm(forms.ModelForm):
    container_size = forms.ChoiceField(
        choices=ContainerSize.choices,
        required=False,
        label="ابعاد کانتینر"
    )

    container_type = forms.ChoiceField(
        choices=ContainerType.choices,
        required=False,
        label="نوع کانتینر"
    )

    container_count = forms.IntegerField(
        min_value=1,
        required=False,
        label="تعداد کانتینر",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'مثال: 2'
        })
    )

    origin_country = forms.ModelChoiceField(
        queryset=Country.objects.filter(is_active=True),
        label="کشور مبدا",
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select',
            # ظاهر فیلد قابل تغییر نیست، ولی چون disabled نیست در POST ارسال می‌شود
            'style': 'pointer-events: none; background-color: #e9ecef;',
            'tabindex': '-1'
        })
    )

    origin_province = forms.ModelChoiceField(
        queryset=Province.objects.none(),
        label="استان مبدا",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    destination_country = forms.ModelChoiceField(
        queryset=Country.objects.filter(is_active=True),
        label="کشور مقصد",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    destination_city = forms.ModelChoiceField(
        queryset=DestinationCity.objects.none(),
        label="شهر مقصد",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    needs_office_packaging = forms.BooleanField(
        required=False,
        label="نیاز به بسته‌بندی در دفتر دارم",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    needs_onsite_packaging = forms.BooleanField(
        required=False,
        label="نیاز به بسته‌بندی در محل دارم",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    needs_doorstep_packaging = forms.BooleanField(
        required=False,
        label="نیاز به حمل و بسته‌بندی در محل دارم",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )

    actual_weight = forms.DecimalField(
        required=False,
        label="وزن واقعی (kg)",
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'مثال: 150'
        })
    )

    class Meta:
        model = CargoRequest
        fields = [
            'origin_country',
            'origin_province',
            'origin_city',
            'destination_country',
            'destination_city',
            'transport_mode',
            'destination_port',
            'cargo_type',
            'actual_weight',
            'shipping_procedure',

            # Packaging services
            'needs_office_packaging',
            'needs_onsite_packaging',
            'needs_doorstep_packaging',
        ]


        widgets = {
            'origin_city': forms.Select(attrs={'class': 'form-select'}),
            'destination_port': forms.Select(attrs={'class': 'form-select'}),
            'shipping_procedure': forms.Select(attrs={'class': 'form-select'}),
            'transport_mode': forms.Select(attrs={'class': 'form-select'}),
            'cargo_type': forms.Select(attrs={'class': 'form-select'}),
            'actual_weight': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 150'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from rates.models import Rate
        from django.utils import timezone

        iran = Country.objects.filter(code='IRN', is_active=True).first()

        if iran:
            self.fields['origin_country'].initial = iran

        self.fields['origin_city'].queryset = City.objects.none()
        self.fields['destination_port'].queryset = Port.objects.none()
        self.fields['destination_city'].queryset = DestinationCity.objects.none()

        # نرخ‌های فعال و منقضی‌نشده
        active_rates = Rate.objects.filter(
            is_active=True,
            valid_until__gte=timezone.now().date()
        )

        # کشور مبدا
        origin_country_id = None

        if self.data.get('origin_country'):
            try:
                origin_country_id = int(self.data.get('origin_country'))
            except (ValueError, TypeError):
                origin_country_id = iran.id if iran else None
        elif self.instance and getattr(self.instance, 'origin_country_id', None):
            origin_country_id = self.instance.origin_country_id
        elif iran:
            origin_country_id = iran.id

        # استان‌های مبدا: فقط استان‌هایی که نرخ فعال دارند
        rated_province_ids = active_rates.values_list('origin_province_id', flat=True).distinct()
        if origin_country_id:
            self.fields['origin_province'].queryset = Province.objects.filter(
                country_id=origin_country_id,
                is_active=True,
                id__in=rated_province_ids
            )
        else:
            self.fields['origin_province'].queryset = Province.objects.filter(
                is_active=True,
                id__in=rated_province_ids
            )

        # مبدا انتخابی (برای فیلتر کردن مقصد)
        transport_mode_val = self.data.get('transport_mode') if self.data else None
        origin_province_id_val = None
        origin_city_id_val = None
        if self.data:
            try:
                origin_province_id_val = int(self.data.get('origin_province') or 0) or None
            except (ValueError, TypeError):
                pass
            try:
                origin_city_id_val = int(self.data.get('origin_city') or 0) or None
            except (ValueError, TypeError):
                pass

        def apply_origin(rates):
            """نرخ‌ها را بر اساس مبدا انتخابی فیلتر کن."""
            if origin_city_id_val:
                return rates.filter(origin_city_id=origin_city_id_val)
            if origin_province_id_val:
                return rates.filter(origin_province_id=origin_province_id_val)
            return rates

        # کشور مقصد: فقط کشورهایی که با مبدا + روش حمل انتخابی نرخ فعال دارند
        dest_country_rates = apply_origin(active_rates)
        if transport_mode_val:
            dest_country_rates = dest_country_rates.filter(transport_mode=transport_mode_val)
        rated_dest_country_ids = dest_country_rates.values_list('destination_country_id', flat=True).distinct()
        self.fields['destination_country'].queryset = Country.objects.filter(
            is_active=True,
            id__in=rated_dest_country_ids
        )

        # شهرهای مبدا: فقط شهرهایی که برای استان انتخابی نرخ فعال دارند
        if 'origin_province' in self.data:
            try:
                province_id = int(self.data.get('origin_province'))
                rated_city_ids = active_rates.filter(
                    origin_province_id=province_id
                ).values_list('origin_city_id', flat=True).distinct()
                self.fields['origin_city'].queryset = City.objects.filter(
                    province_id=province_id,
                    is_active=True,
                    id__in=rated_city_ids
                )
            except (ValueError, TypeError):
                pass
        elif self.instance and getattr(self.instance, 'origin_province_id', None):
            rated_city_ids = active_rates.filter(
                origin_province_id=self.instance.origin_province_id
            ).values_list('origin_city_id', flat=True).distinct()
            self.fields['origin_city'].queryset = City.objects.filter(
                province_id=self.instance.origin_province_id,
                is_active=True,
                id__in=rated_city_ids
            )

        # شهرهای مقصد: فقط شهرهایی که برای مبدا + کشور + روش حمل نرخ فعال دارند
        if 'destination_country' in self.data:
            try:
                country_id = int(self.data.get('destination_country'))
                city_rates = apply_origin(active_rates).filter(destination_country_id=country_id)
                if transport_mode_val:
                    city_rates = city_rates.filter(transport_mode=transport_mode_val)
                rated_dest_city_ids = city_rates.values_list('destination_city_id', flat=True).distinct()
                self.fields['destination_city'].queryset = DestinationCity.objects.filter(
                    country_id=country_id,
                    is_active=True,
                    id__in=rated_dest_city_ids
                )
            except (ValueError, TypeError):
                pass
        elif self.instance and getattr(self.instance, 'destination_country_id', None):
            self.fields['destination_city'].queryset = DestinationCity.objects.filter(
                country_id=self.instance.destination_country_id,
                is_active=True,
            )

        # پورت مقصد: فقط پورت‌هایی که برای مبدا + شهر + روش حمل نرخ فعال دارند
        if 'destination_city' in self.data:
            try:
                city_id = int(self.data.get('destination_city'))
                port_rates = apply_origin(active_rates).filter(destination_city_id=city_id)
                if transport_mode_val:
                    port_rates = port_rates.filter(transport_mode=transport_mode_val)
                rated_port_ids = port_rates.values_list('destination_port_id', flat=True).distinct()
                ports = Port.objects.filter(city_id=city_id, is_active=True, id__in=rated_port_ids)
                if transport_mode_val:
                    if 'sea' in transport_mode_val:
                        ports = ports.filter(port_type='sea')
                    elif 'air' in transport_mode_val:
                        ports = ports.filter(port_type='air')
                    elif 'land' in transport_mode_val:
                        ports = ports.filter(port_type='land')
                    elif 'rail' in transport_mode_val:
                        ports = ports.filter(port_type='rail')
                self.fields['destination_port'].queryset = ports
            except (ValueError, TypeError):
                pass
        elif self.instance and getattr(self.instance, 'destination_city_id', None):
            self.fields['destination_port'].queryset = Port.objects.filter(
                city_id=self.instance.destination_city_id
            )

    def clean_origin_country(self):
        """
        کشور مبدا در فرم مشتری فعلاً باید ایران باشد.
        حتی اگر کاربر از DevTools مقدار را تغییر دهد، اینجا دوباره ایران ست می‌شود.
        """

        iran = Country.objects.filter(code='IRN', is_active=True).first()

        if iran:
            return iran

        return self.cleaned_data.get('origin_country')

    def clean(self):
        cleaned_data = super().clean()

        transport_mode = cleaned_data.get('transport_mode')
        actual_weight = cleaned_data.get('actual_weight')

        if transport_mode in ['sea_fcl', 'FCL']:
            if not cleaned_data.get('container_type'):
                self.add_error('container_type', 'برای حمل FCL، انتخاب نوع کانتینر الزامی است.')

            if not cleaned_data.get('container_count'):
                self.add_error('container_count', 'برای حمل FCL، تعیین تعداد کانتینر الزامی است.')

            if actual_weight is None:
                cleaned_data['actual_weight'] = 0

        else:
            if actual_weight is None:
                self.add_error('actual_weight', 'وارد کردن وزن واقعی برای این روش حمل الزامی است.')

        return cleaned_data


class CargoDimensionForm(forms.ModelForm):
    class Meta:
        model = CargoDimension
        fields = ['length', 'width', 'height', 'quantity']
        widgets = {
            'length': forms.NumberInput(attrs={'class': 'form-control dimension-input', 'placeholder': 'طول (cm)'}),
            'width': forms.NumberInput(attrs={'class': 'form-control dimension-input', 'placeholder': 'عرض (cm)'}),
            'height': forms.NumberInput(attrs={'class': 'form-control dimension-input', 'placeholder': 'ارتفاع (cm)'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'value': 1}),
        }

CargoDimensionFormSet = inlineformset_factory(
    CargoRequest, CargoDimension, form=CargoDimensionForm,
    extra=1, can_delete=True
)


class OrderCompletionForm(forms.ModelForm):
    is_for_other = forms.BooleanField(
        required=False,
        label="ثبت سفارش برای فرد دیگری است",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'is_for_other_checkbox'
        })
    )
 
    # فیلدهای مجزای نام و نام خانوادگی فرستنده
    sender_first_name = forms.CharField(
        label="نام فرستنده",
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
 
    sender_last_name = forms.CharField(
        label="نام خانوادگی فرستنده",
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
 
    class Meta:
        model = CargoRequest
        fields = [
            'sender_national_id',
            'sender_phone',
            'sender_province',
            'sender_city',
            'sender_address',
            'other_cargo_details',
        ]
 
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
 
        # ── مقداردهی اولیه (فقط در GET) ─────────────────────────
        if self.user and not self.data:
            self.initial['sender_first_name'] = self.user.first_name
            self.initial['sender_last_name'] = self.user.last_name
            self.initial['sender_phone'] = getattr(self.user, 'mobile', '')
 
            national_id = ''
            address = ''
            if hasattr(self.user, 'customer_profile') and self.user.customer_profile:
                national_id = self.user.customer_profile.national_code
                address = self.user.customer_profile.address or ''
            elif hasattr(self.user, 'customer_company_profile') and self.user.customer_company_profile:
                national_id = self.user.customer_company_profile.national_id
                address = self.user.customer_company_profile.address or ''
 
            self.initial['sender_national_id'] = national_id
            # آدرس از پروفایل کاربر — مرحله ۲
            if not self.initial.get('sender_address'):
                self.initial['sender_address'] = address
 
        # اگر instance قبلاً sender_name داشت، آن را به دو بخش بشکن
        if self.instance and self.instance.pk and self.instance.sender_name and not self.data:
            parts = self.instance.sender_name.strip().split(' ', 1)
            self.initial['sender_first_name'] = parts[0]
            self.initial['sender_last_name'] = parts[1] if len(parts) > 1 else ''
 
        # ── قفل کردن استان و شهر مبدا ───────────────────────────
        if self.instance and self.instance.origin_city:
            self.initial['sender_city'] = self.instance.origin_city
            if hasattr(self.instance.origin_city, 'province'):
                self.initial['sender_province'] = self.instance.origin_city.province
            self.fields['sender_city'].disabled = True
            self.fields['sender_province'].disabled = True
 
        # ── کلاس‌بندی ───────────────────────────────────────────
        self.fields['sender_address'].widget.attrs.update({'rows': 3, 'class': 'form-control'})
        self.fields['sender_national_id'].widget.attrs.update({'class': 'form-control'})
        self.fields['sender_phone'].widget.attrs.update({'class': 'form-control'})
 
    def clean_sender_national_id(self):
        """اعتبارسنجی کد ملی فرستنده با الگوریتم استاندارد."""
        value = self.cleaned_data.get('sender_national_id')
        if value:
            validate_iranian_national_code(value)
        return value
 
    def clean(self):
        cleaned_data = super().clean()
 
        # برگرداندن استان و شهر (چون disabled هستند و در POST نمی‌آیند)
        if self.instance and self.instance.origin_city:
            cleaned_data['sender_city'] = self.instance.origin_city
            if hasattr(self.instance.origin_city, 'province'):
                cleaned_data['sender_province'] = self.instance.origin_city.province
 
        # اعتبارسنجی فیلدهای اجباری
        if not cleaned_data.get('sender_first_name'):
            self.add_error('sender_first_name', 'نام فرستنده الزامی است.')
        if not cleaned_data.get('sender_last_name'):
            self.add_error('sender_last_name', 'نام خانوادگی فرستنده الزامی است.')
        if not cleaned_data.get('sender_national_id'):
            self.add_error('sender_national_id', 'کد ملی فرستنده الزامی است.')
        if not cleaned_data.get('sender_phone'):
            self.add_error('sender_phone', 'شماره تماس فرستنده الزامی است.')
 
        return cleaned_data
 
    def save(self, commit=True):
        """ترکیب نام و نام خانوادگی در فیلد sender_name مدل."""
        instance = super().save(commit=False)
        first = self.cleaned_data.get('sender_first_name', '').strip()
        last = self.cleaned_data.get('sender_last_name', '').strip()
        instance.sender_name = f"{first} {last}".strip()
        if commit:
            instance.save()
            self.save_m2m()
        return instance