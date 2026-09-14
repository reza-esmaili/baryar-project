from django import forms
from accounts.models import User,CustomerProfile, CustomerCompanyProfile, IdentityDocument
from core.validators import validate_iranian_national_code

class LoginForm(forms.Form):
    mobile = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'شماره موبایل'}), label='شماره موبایل')
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'رمز عبور'}), label='رمز عبور')

class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'رمز عبور'}), label='رمز عبور')
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'mobile', 'password']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'نام'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'نام خانوادگی'}),
            'mobile': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'شماره موبایل'}),
        }
        labels = {
            'first_name': 'نام',
            'last_name': 'نام خانوادگی',
            'mobile': 'شماره موبایل',
        }

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        # فیلد mobile را از اینجا حذف کردیم تا خطای Duplicate ندهد
        fields = [
            "first_name",
            "last_name",
            "email",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }
        labels = {
            "first_name": "نام",
            "last_name": "نام خانوادگی",
            "email": "ایمیل (اختیاری)",
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email:
            return email
        # بررسی تکراری نبودن ایمیل در بین کاربران دیگر
        qs = User.objects.filter(email=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("این ایمیل قبلاً توسط کاربر دیگری ثبت شده است.")
        return email


class CustomerProfileForm(forms.ModelForm):
 
    class Meta:
        model = CustomerProfile
        fields = [
            "national_code",
            "address"
        ]
        widgets = {
            "national_code": forms.TextInput(attrs={
                "class": "form-control",
                "maxlength": "10",
                "placeholder": "کد ملی ۱۰ رقمی",
            }),
            "address": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3
            })
        }
 
    def clean_national_code(self):
        """اعتبارسنجی کد ملی با الگوریتم استاندارد."""
        value = self.cleaned_data.get("national_code")
        if value:
            # validate_iranian_national_code در صورت نامعتبر بودن
            # ValidationError با پیام فارسی پرتاب می‌کند
            validate_iranian_national_code(value)
        return value

class CompanyProfileForm(forms.ModelForm):

    class Meta:
        model = CustomerCompanyProfile

        exclude = ["user"]


class IdentityDocumentForm(forms.ModelForm):

    ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "pdf"]
    MAX_FILE_SIZE_MB = 5

    class Meta:
        model = IdentityDocument

        fields = [
            "doc_type",
            "file"
        ]

        widgets = {
            "doc_type": forms.Select(attrs={
                "class": "form-select"
            }),

            "file": forms.FileInput(attrs={
                "class": "form-control"
            })
        }

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if not file:
            return file

        ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
        if ext not in self.ALLOWED_EXTENSIONS:
            raise forms.ValidationError(
                f"پسوند فایل مجاز نیست. پسوندهای مجاز: {', '.join(self.ALLOWED_EXTENSIONS)}"
            )

        max_size = self.MAX_FILE_SIZE_MB * 1024 * 1024
        if file.size > max_size:
            raise forms.ValidationError(
                f"حجم فایل نباید بیشتر از {self.MAX_FILE_SIZE_MB} مگابایت باشد."
            )

        return file