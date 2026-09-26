from django.db import models
from accounts.models import User, CompanyType
from locations.models import Province, City
from core.models import TimeStampedModel


class ServiceCategory(models.TextChoices):
    """دسته‌های خدمات شرکت حمل؛ ALL برای مدارک مشترک همه‌ی شرکت‌ها."""
    ALL = "all", "همه‌ی شرکت‌ها"
    AIR = "air", "حمل هوایی"
    SEA = "sea", "حمل دریایی"
    LAND_INTRACITY = "land_intracity", "حمل زمینی درون‌شهری"
    LAND_DOMESTIC = "land_domestic", "حمل زمینی برون‌شهری (داخلی)"
    LAND_INTERNATIONAL = "land_international", "حمل زمینی بین‌المللی"


# فیلد دسته روی ForwarderCompany برای هر ServiceCategory (به‌جز ALL)
SERVICE_FIELD = {
    ServiceCategory.AIR: "service_air",
    ServiceCategory.SEA: "service_sea",
    ServiceCategory.LAND_INTRACITY: "service_land_intracity",
    ServiceCategory.LAND_DOMESTIC: "service_land_domestic",
    ServiceCategory.LAND_INTERNATIONAL: "service_land_international",
}


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

    # دسته‌های خدمات شرکت. یک شرکت می‌تواند در چند دسته فعال باشد. هوایی و
    # دریایی از مسیر نرخ‌گذاری کار می‌کنند؛ سه دسته‌ی زمینی از مسیر «اعلام بار»
    # (درخواست مشتری → ارسال به شرکت‌های واجد شرایط → اولین پذیرنده).
    service_air = models.BooleanField(default=False, verbose_name="حمل هوایی")
    service_sea = models.BooleanField(default=False, verbose_name="حمل دریایی")
    service_land_intracity = models.BooleanField(default=False, verbose_name="حمل زمینی درون‌شهری")
    service_land_domestic = models.BooleanField(default=False, verbose_name="حمل زمینی برون‌شهری (داخلی)")
    service_land_international = models.BooleanField(default=False, verbose_name="حمل زمینی بین‌المللی")

    @property
    def offers_land(self):
        return self.service_land_intracity or self.service_land_domestic or self.service_land_international

    @property
    def offers_rates(self):
        """هوایی/دریایی؛ یعنی نرخ‌گذاری و سفارش‌های نرخ‌محور."""
        return self.service_air or self.service_sea

    @property
    def is_operational(self):
        return self.is_verified and self.is_active

    def active_service_categories(self):
        return [category for category, field in SERVICE_FIELD.items() if getattr(self, field)]

    def document_requirements(self):
        """مدارک ثبت‌نامِ لازم برای دسته‌های فعلی شرکت (مشترک + هر دسته)."""
        return CompanyDocumentRequirement.for_categories(self.active_service_categories())

    def allowed_rate_transport_modes(self):
        from rates.models import TransportMode

        modes = []
        if self.service_air:
            modes.append(TransportMode.AIR)
        if self.service_sea:
            modes.extend([TransportMode.SEA_FCL, TransportMode.SEA_LCL])
        return modes

    def service_labels(self):
        labels = []
        for field in (
            "service_air", "service_sea", "service_land_intracity",
            "service_land_domestic", "service_land_international",
        ):
            if getattr(self, field):
                labels.append(self._meta.get_field(field).verbose_name)
        return labels

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

    # حمل زمینی (اعلام بار)
    can_view_land_requests = models.BooleanField(default=False, verbose_name="مشاهده درخواست‌های حمل زمینی")
    can_accept_land_requests = models.BooleanField(default=False, verbose_name="پذیرش و پیگیری درخواست‌های حمل زمینی")

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


class CompanyDocumentRequirement(TimeStampedModel):
    """
    مدرکی که شرکت حمل هنگام ثبت‌نام باید بارگذاری کند. مدیر پلتفرم تعیین
    می‌کند هر مدرک برای کدام دسته‌ی خدمات لازم است (یا برای همه).
    """

    document_type = models.ForeignKey(
        "documents.DocumentType",
        on_delete=models.PROTECT,
        related_name="company_requirements",
        verbose_name="نوع مدرک",
    )
    service = models.CharField(
        max_length=30, choices=ServiceCategory.choices, default=ServiceCategory.ALL,
        verbose_name="برای دسته‌ی خدمات",
    )
    is_required = models.BooleanField(default=True, verbose_name="اجباری")
    guidance = models.CharField(
        max_length=255, blank=True, verbose_name="راهنما برای شرکت",
        help_text="توضیح کوتاهی که کنار فیلد بارگذاری به شرکت نمایش داده می‌شود.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name="ترتیب نمایش")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "مدرک ثبت‌نام شرکت حمل"
        verbose_name_plural = "مدارک ثبت‌نام شرکت‌های حمل"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["document_type", "service"], name="uniq_company_doc_req_type_service"),
        ]

    def __str__(self):
        return f"{self.document_type.title} — {self.get_service_display()}"

    @classmethod
    def for_categories(cls, categories):
        return cls.objects.filter(
            is_active=True,
            document_type__is_active=True,
            service__in=[ServiceCategory.ALL, *categories],
        ).select_related("document_type")
