from django.db import models
from accounts.models import User, CompanyType
from locations.models import Province, City
from core.models import TimeStampedModel


class ForwarderCompany(TimeStampedModel):
    """شرکت فورواردر مادر"""
    admin_user = models.OneToOneField(
        User, on_delete=models.PROTECT, related_name="forwarder_company",
        limit_choices_to={"role": User.Role.FORWARDER_ADMIN}
    )
    company_name = models.CharField(max_length=255, verbose_name="نام شرکت") 
    company_type = models.CharField(max_length=30, choices=CompanyType.choices)
    national_id = models.CharField(max_length=11, unique=True)
    registration_number = models.CharField(max_length=20, unique=True)
    ceo_first_name = models.CharField(max_length=100)
    ceo_last_name = models.CharField(max_length=100)
    ceo_national_code = models.CharField(max_length=10)
    phone = models.CharField(max_length=15)
    email = models.EmailField()
    postal_code = models.CharField(max_length=10)
    address = models.TextField()
    logo = models.ImageField(upload_to="forwarder_logos/", null=True, blank=True)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    instagram = models.CharField(max_length=100, blank=True)
    linkedin = models.CharField(max_length=100, blank=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.national_id

    class Meta:
        verbose_name = "شرکت فورواردر"
        verbose_name_plural = "شرکت‌های فورواردر"


class ForwarderBranch(TimeStampedModel):
    """شعبه فورواردر — اکانت مستقل دارد"""
    company = models.ForeignKey(ForwarderCompany, on_delete=models.CASCADE, related_name="branches")
    branch_user = models.OneToOneField(
        User, on_delete=models.PROTECT, related_name="forwarder_branch"
    )
    name = models.CharField(max_length=200)
    representative_first_name = models.CharField(max_length=100)
    representative_last_name = models.CharField(max_length=100)
    representative_mobile = models.CharField(max_length=15)
    province = models.ForeignKey(Province, on_delete=models.PROTECT)
    city = models.ForeignKey(City, on_delete=models.PROTECT)
    address = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.company} - {self.name}"

    class Meta:
        verbose_name = "شعبه فورواردر"
        verbose_name_plural = "شعب فورواردر"


class ForwarderStaff(TimeStampedModel):
    """کارمندان شرکت فورواردر"""
    company = models.ForeignKey(ForwarderCompany, on_delete=models.CASCADE, related_name="staff")
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="forwarder_staff")
    role = models.ForeignKey(
        'ForwarderRole',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='staff_members',
        verbose_name="نقش"
    )
    national_code = models.CharField(max_length=10, blank=True, verbose_name="کد ملی")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    def __str__(self):
        return f"{self.user} @ {self.company}"

    class Meta:
        verbose_name = "کارمند فورواردر"
        verbose_name_plural = "کارمندان فورواردر"


class ForwarderRole(TimeStampedModel):
    """نقش‌های دسترسی برای کارمندان شرکت فورواردر"""
    company = models.ForeignKey(ForwarderCompany, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=100, verbose_name="نام نقش")

    # سفارشات
    can_view_orders = models.BooleanField(default=False, verbose_name="مشاهده سفارشات")
    can_manage_orders = models.BooleanField(default=False, verbose_name="مدیریت سفارشات")
    can_update_order_status = models.BooleanField(default=False, verbose_name="تغییر وضعیت سفارش")
    can_send_order_message = models.BooleanField(default=False, verbose_name="ارسال پیام در سفارش")
    can_request_documents = models.BooleanField(default=False, verbose_name="درخواست مدارک از مشتری")

    # نرخ‌ها
    can_view_rates = models.BooleanField(default=False, verbose_name="مشاهده نرخ‌ها")
    can_create_rates = models.BooleanField(default=False, verbose_name="ایجاد نرخ جدید")
    can_edit_rates = models.BooleanField(default=False, verbose_name="ویرایش نرخ‌ها")
    can_delete_rates = models.BooleanField(default=False, verbose_name="حذف نرخ‌ها")
    can_bulk_upload_rates = models.BooleanField(default=False, verbose_name="آپلود گروهی نرخ")

    # شعب و کارمندان
    can_view_branches = models.BooleanField(default=False, verbose_name="مشاهده شعب")
    can_manage_branches = models.BooleanField(default=False, verbose_name="مدیریت شعب")
    can_view_staff = models.BooleanField(default=False, verbose_name="مشاهده کارمندان")
    can_manage_staff = models.BooleanField(default=False, verbose_name="مدیریت کارمندان")

    # گزارشات و مالی
    can_view_reports = models.BooleanField(default=False, verbose_name="مشاهده گزارشات")
    can_export_reports = models.BooleanField(default=False, verbose_name="خروجی گرفتن از گزارشات")

    # مدارک
    can_view_documents = models.BooleanField(default=False, verbose_name="مشاهده مدارک")
    can_manage_documents = models.BooleanField(default=False, verbose_name="تایید/رد مدارک")

    # پشتیبانی
    can_view_support = models.BooleanField(default=False, verbose_name="مشاهده تیکت‌های پشتیبانی")
    can_reply_support = models.BooleanField(default=False, verbose_name="پاسخ به تیکت‌های پشتیبانی")

    # تنظیمات
    can_view_settings = models.BooleanField(default=False, verbose_name="مشاهده تنظیمات")
    can_manage_roles = models.BooleanField(default=False, verbose_name="مدیریت نقش‌ها و دسترسی‌ها")
    can_upload_logo = models.BooleanField(default=False, verbose_name="آپلود لوگو شرکت")

    def __str__(self):
        return f"{self.name} — {self.company}"

    class Meta:
        verbose_name = "نقش فورواردر"
        verbose_name_plural = "نقش‌های فورواردر"
        unique_together = [("company", "name")]
