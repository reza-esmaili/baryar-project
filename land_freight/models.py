from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


def local_today():
    # پروژه با USE_TZ=False اجرا می‌شود و timezone.localdate() روی زمان naive خطا می‌دهد.
    now = timezone.now()
    return timezone.localtime(now).date() if timezone.is_aware(now) else now.date()


class VehicleType(TimeStampedModel):
    """کلاس ناوگان بر اساس ظرفیت (وانت، نیسان، کامیونت، تریلی...)."""

    name = models.CharField(max_length=100, unique=True, verbose_name="نام")
    capacity_kg = models.PositiveIntegerField(null=True, blank=True, verbose_name="ظرفیت تقریبی (کیلوگرم)")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "نوع ناوگان"
        verbose_name_plural = "انواع ناوگان"
        ordering = ["capacity_kg", "name"]


class LoaderType(TimeStampedModel):
    """نوع بارگیر/بدنه (چادری، کفی، یخچالی...). برای شرکت حمل اطلاع‌رسانی است، نه معیار تطبیق."""

    name = models.CharField(max_length=100, unique=True, verbose_name="نام")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "نوع بارگیر"
        verbose_name_plural = "انواع بارگیر"
        ordering = ["name"]


class LandServiceScope(models.TextChoices):
    INTRACITY = "intracity", "درون‌شهری"
    DOMESTIC = "domestic", "برون‌شهری (داخل ایران)"
    INTERNATIONAL = "international", "بین‌المللی"


# فیلد دسته‌ی خدمات متناظر با هر حوزه روی ForwarderCompany
SCOPE_COMPANY_FLAG = {
    LandServiceScope.INTRACITY: "service_land_intracity",
    LandServiceScope.DOMESTIC: "service_land_domestic",
    LandServiceScope.INTERNATIONAL: "service_land_international",
}

# مهلت پذیرش پیش از انقضای خودکار درخواست
EXPIRY_HOURS = {
    LandServiceScope.INTRACITY: 3,
    LandServiceScope.DOMESTIC: 24,
    LandServiceScope.INTERNATIONAL: 72,
}


class LandCarrierProfile(TimeStampedModel):
    """حوزه‌ی فعالیت یک شرکت در حمل زمینی — مبنای تطبیق درخواست‌ها با شرکت."""

    company = models.OneToOneField(
        "forwarders.ForwarderCompany",
        on_delete=models.CASCADE,
        related_name="land_profile",
        verbose_name="شرکت",
    )
    service_cities = models.ManyToManyField(
        "locations.City",
        blank=True,
        related_name="land_carriers",
        verbose_name="شهرهای تحت پوشش (درون‌شهری)",
    )
    service_countries = models.ManyToManyField(
        "locations.Country",
        blank=True,
        related_name="land_carriers",
        verbose_name="کشورهای تحت پوشش (بین‌المللی)",
        help_text="اگر خالی بماند، شرکت برای همه‌ی کشورها درخواست دریافت می‌کند.",
    )
    vehicle_types = models.ManyToManyField(
        VehicleType,
        blank=True,
        related_name="carrier_profiles",
        verbose_name="ناوگان در اختیار",
    )

    def __str__(self):
        return f"حوزه‌ی حمل زمینی {self.company.company_name}"

    class Meta:
        verbose_name = "حوزه‌ی فعالیت حمل زمینی"
        verbose_name_plural = "حوزه‌های فعالیت حمل زمینی"


class InternationalDirection(models.TextChoices):
    EXPORT = "export", "از ایران به خارج (صادرات)"
    IMPORT = "import", "از خارج به ایران (واردات)"


class PickupWindow(models.TextChoices):
    ANY = "any", "در طول روز"
    MORNING = "morning", "صبح (۶ تا ۱۲)"
    AFTERNOON = "afternoon", "ظهر و عصر (۱۲ تا ۱۸)"
    EVENING = "evening", "شب (۱۸ تا ۲۴)"


class PackagingType(models.TextChoices):
    PALLET = "pallet", "پالت"
    CARTON = "carton", "کارتن"
    BAG = "bag", "کیسه"
    BULK = "bulk", "فله"
    CRATE = "crate", "جعبه چوبی"
    DRUM = "drum", "بشکه"
    ROLL = "roll", "رول"
    MACHINERY = "machinery", "ماشین‌آلات / قطعه‌ی حجیم"
    OTHER = "other", "سایر"


class LandRequestStatus(models.TextChoices):
    OPEN = "open", "در انتظار پذیرش شرکت حمل"
    ASSIGNED = "assigned", "پذیرفته شده"
    IN_TRANSIT = "in_transit", "در حال حمل"
    DELIVERED = "delivered", "تحویل شده"
    CANCELLED = "cancelled", "لغو شده"
    EXPIRED = "expired", "منقضی شده (بدون پذیرش)"


ACTIVE_ASSIGNED_STATUSES = (LandRequestStatus.ASSIGNED, LandRequestStatus.IN_TRANSIT)


class LandFreightRequest(TimeStampedModel):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="land_requests",
        verbose_name="مشتری",
    )
    scope = models.CharField(max_length=20, choices=LandServiceScope.choices, db_index=True, verbose_name="نوع حمل")
    direction = models.CharField(
        max_length=10, choices=InternationalDirection.choices, blank=True, verbose_name="جهت حمل بین‌المللی",
    )

    # سمت ایرانی مسیر؛ در درون‌شهری مبدا و مقصد یک شهرند.
    origin_city = models.ForeignKey(
        "locations.City", on_delete=models.PROTECT, null=True, blank=True,
        related_name="land_origin_requests", verbose_name="شهر مبدا",
    )
    destination_city = models.ForeignKey(
        "locations.City", on_delete=models.PROTECT, null=True, blank=True,
        related_name="land_destination_requests", verbose_name="شهر مقصد",
    )
    # سمت خارجی مسیر (فقط بین‌المللی)
    foreign_country = models.ForeignKey(
        "locations.Country", on_delete=models.PROTECT, null=True, blank=True,
        related_name="land_requests", verbose_name="کشور طرف خارجی",
    )
    foreign_city = models.ForeignKey(
        "locations.DestinationCity", on_delete=models.PROTECT, null=True, blank=True,
        related_name="land_requests", verbose_name="شهر طرف خارجی",
    )
    foreign_city_name = models.CharField(
        max_length=150, blank=True, verbose_name="نام شهر خارجی (اگر در فهرست نیست)",
    )
    border_crossing = models.ForeignKey(
        "locations.Port", on_delete=models.PROTECT, null=True, blank=True,
        related_name="land_requests", limit_choices_to={"port_type": "land"},
        verbose_name="مرز / گمرک خروجی ترجیحی",
    )

    pickup_address = models.TextField(verbose_name="آدرس بارگیری")
    delivery_address = models.TextField(verbose_name="آدرس تخلیه")
    pickup_date = models.DateField(verbose_name="تاریخ بارگیری")
    pickup_window = models.CharField(
        max_length=10, choices=PickupWindow.choices, default=PickupWindow.ANY, verbose_name="بازه‌ی زمانی بارگیری",
    )

    cargo_type = models.ForeignKey(
        "rates.CargoType", on_delete=models.PROTECT, related_name="land_requests", verbose_name="نوع کالا",
    )
    cargo_description = models.CharField(max_length=255, verbose_name="شرح کالا")
    weight_kg = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="وزن (کیلوگرم)")
    volume_cbm = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="حجم (متر مکعب)",
    )
    package_count = models.PositiveIntegerField(null=True, blank=True, verbose_name="تعداد بسته")
    packaging_type = models.CharField(
        max_length=20, choices=PackagingType.choices, default=PackagingType.CARTON, verbose_name="نوع بسته‌بندی",
    )
    cargo_value = models.DecimalField(
        max_digits=18, decimal_places=0, null=True, blank=True, verbose_name="ارزش تقریبی کالا (ریال)",
    )
    is_hazardous = models.BooleanField(default=False, verbose_name="کالای خطرناک")
    is_fragile = models.BooleanField(default=False, verbose_name="شکستنی")
    needs_refrigeration = models.BooleanField(default=False, verbose_name="نیاز به یخچال/کنترل دما")

    vehicle_type = models.ForeignKey(
        VehicleType, on_delete=models.PROTECT, related_name="requests", verbose_name="نوع ناوگان",
    )
    loader_type = models.ForeignKey(
        LoaderType, on_delete=models.PROTECT, null=True, blank=True, related_name="requests", verbose_name="نوع بارگیر",
    )
    needs_loading_help = models.BooleanField(default=False, verbose_name="نیاز به کارگر بارگیری/تخلیه")
    needs_insurance = models.BooleanField(default=False, verbose_name="نیاز به بیمه‌ی بار")
    needs_customs_clearance = models.BooleanField(default=False, verbose_name="نیاز به ترخیص/اظهار گمرکی")

    sender_name = models.CharField(max_length=150, verbose_name="نام تحویل‌دهنده")
    sender_phone = models.CharField(max_length=15, verbose_name="تلفن تحویل‌دهنده")
    receiver_name = models.CharField(max_length=150, verbose_name="نام تحویل‌گیرنده")
    receiver_phone = models.CharField(max_length=15, verbose_name="تلفن تحویل‌گیرنده")

    proposed_price = models.DecimalField(max_digits=18, decimal_places=0, verbose_name="کرایه‌ی پیشنهادی (ریال)")
    notes = models.TextField(blank=True, verbose_name="توضیحات")

    status = models.CharField(
        max_length=20, choices=LandRequestStatus.choices, default=LandRequestStatus.OPEN,
        db_index=True, verbose_name="وضعیت",
    )
    expires_at = models.DateTimeField(verbose_name="مهلت پذیرش")

    assigned_company = models.ForeignKey(
        "forwarders.ForwarderCompany", on_delete=models.PROTECT, null=True, blank=True,
        related_name="assigned_land_requests", verbose_name="شرکت پذیرنده",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="accepted_land_requests", verbose_name="پذیرفته شده توسط",
    )
    assigned_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان پذیرش")
    agreed_price = models.DecimalField(
        max_digits=18, decimal_places=0, null=True, blank=True, verbose_name="کرایه‌ی توافق‌شده (ریال)",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان لغو")
    cancel_reason = models.CharField(max_length=255, blank=True, verbose_name="دلیل لغو")

    class Meta:
        verbose_name = "درخواست حمل زمینی"
        verbose_name_plural = "درخواست‌های حمل زمینی"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "expires_at"])]

    def __str__(self):
        return f"{self.reference} ({self.get_scope_display()})"

    @property
    def reference(self):
        return f"LF-{self.pk:06d}" if self.pk else "LF-new"

    @staticmethod
    def default_expiry(scope, now=None):
        return (now or timezone.now()) + timedelta(hours=EXPIRY_HOURS.get(scope, 24))

    @property
    def is_open_for_acceptance(self):
        return self.status == LandRequestStatus.OPEN and self.expires_at > timezone.now()

    @property
    def foreign_city_display(self):
        if self.foreign_city_id:
            return self.foreign_city.name
        return self.foreign_city_name

    @property
    def origin_display(self):
        if self.scope == LandServiceScope.INTERNATIONAL and self.direction == InternationalDirection.IMPORT:
            parts = [self.foreign_city_display, self.foreign_country.name if self.foreign_country_id else ""]
            return "، ".join(p for p in parts if p)
        return self.origin_city.name if self.origin_city_id else ""

    @property
    def destination_display(self):
        if self.scope == LandServiceScope.INTERNATIONAL and self.direction == InternationalDirection.EXPORT:
            parts = [self.foreign_city_display, self.foreign_country.name if self.foreign_country_id else ""]
            return "، ".join(p for p in parts if p)
        return self.destination_city.name if self.destination_city_id else ""

    def clean(self):
        super().clean()
        errors = {}

        if self.scope == LandServiceScope.INTRACITY:
            if not self.origin_city_id:
                errors["origin_city"] = "برای حمل درون‌شهری، شهر را انتخاب کنید."
        elif self.scope == LandServiceScope.DOMESTIC:
            if not self.origin_city_id:
                errors["origin_city"] = "شهر مبدا را انتخاب کنید."
            if not self.destination_city_id:
                errors["destination_city"] = "شهر مقصد را انتخاب کنید."
            if self.origin_city_id and self.origin_city_id == self.destination_city_id:
                errors["destination_city"] = "در حمل برون‌شهری، مبدا و مقصد باید دو شهر متفاوت باشند؛ برای جابجایی داخل یک شهر «درون‌شهری» را انتخاب کنید."
        elif self.scope == LandServiceScope.INTERNATIONAL:
            if not self.direction:
                errors["direction"] = "جهت حمل (صادرات یا واردات) را مشخص کنید."
            if not self.foreign_country_id:
                errors["foreign_country"] = "کشور طرف خارجی را انتخاب کنید."
            elif self.foreign_country.code == "IRN":
                errors["foreign_country"] = "در حمل بین‌المللی، کشور طرف خارجی نمی‌تواند ایران باشد."
            if not self.foreign_city_id and not self.foreign_city_name:
                errors["foreign_city"] = "شهر طرف خارجی را انتخاب یا وارد کنید."
            if self.foreign_city_id and self.foreign_country_id and self.foreign_city.country_id != self.foreign_country_id:
                errors["foreign_city"] = "شهر انتخاب‌شده متعلق به این کشور نیست."
            if self.direction == InternationalDirection.EXPORT and not self.origin_city_id:
                errors["origin_city"] = "شهر مبدا در ایران را انتخاب کنید."
            if self.direction == InternationalDirection.IMPORT and not self.destination_city_id:
                errors["destination_city"] = "شهر مقصد در ایران را انتخاب کنید."
            if self.border_crossing_id and self.border_crossing.port_type != "land":
                errors["border_crossing"] = "مرز انتخاب‌شده گمرک زمینی نیست."

        if self.pickup_date and self.pickup_date < local_today():
            errors["pickup_date"] = "تاریخ بارگیری نمی‌تواند در گذشته باشد."
        if self.proposed_price is not None and self.proposed_price <= 0:
            errors["proposed_price"] = "کرایه‌ی پیشنهادی باید بیشتر از صفر باشد."
        if self.weight_kg is not None and self.weight_kg <= 0:
            errors["weight_kg"] = "وزن بار باید بیشتر از صفر باشد."

        if errors:
            raise ValidationError(errors)


class DispatchStatus(models.TextChoices):
    SENT = "sent", "ارسال شده"
    SEEN = "seen", "مشاهده شده"
    ACCEPTED = "accepted", "پذیرفته"
    MISSED = "missed", "توسط شرکت دیگری پذیرفته شد"
    CLOSED = "closed", "بسته شد (لغو یا انقضا)"


class LandRequestDispatch(models.Model):
    """ثبت ارسال یک درخواست به یک شرکت واجد شرایط — مبنای «اولین پذیرنده»."""

    request = models.ForeignKey(LandFreightRequest, on_delete=models.CASCADE, related_name="dispatches")
    company = models.ForeignKey(
        "forwarders.ForwarderCompany", on_delete=models.CASCADE, related_name="land_dispatches",
    )
    status = models.CharField(max_length=10, choices=DispatchStatus.choices, default=DispatchStatus.SENT, db_index=True)
    sent_at = models.DateTimeField(default=timezone.now)
    seen_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "ارسال درخواست به شرکت"
        verbose_name_plural = "ارسال‌های درخواست به شرکت‌ها"
        constraints = [
            models.UniqueConstraint(fields=["request", "company"], name="uniq_land_dispatch_request_company"),
        ]

    def __str__(self):
        return f"{self.request.reference} → {self.company.company_name} ({self.status})"


class LandRequestEvent(models.Model):
    class EventType(models.TextChoices):
        CREATED = "created", "ثبت درخواست"
        DISPATCHED = "dispatched", "ارسال به شرکت‌ها"
        ACCEPTED = "accepted", "پذیرش توسط شرکت حمل"
        STATUS_CHANGED = "status_changed", "تغییر وضعیت"
        CANCELLED = "cancelled", "لغو"
        EXPIRED = "expired", "انقضا"
        REPUBLISHED = "republished", "انتشار مجدد"

    request = models.ForeignKey(LandFreightRequest, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "رویداد درخواست حمل زمینی"
        verbose_name_plural = "رویدادهای درخواست حمل زمینی"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.request.reference}: {self.get_event_type_display()}"
