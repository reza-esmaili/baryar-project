# admin_dashboard/lookups.py
#
# رجیستری تنظیمات برای جدول‌های مرجع/لوکاپ ساده (کشور، استان، شهر، نوع مدرک،
# دپارتمان پشتیبانی و...). به‌جای نوشتن یک ویو و یک تمپلیت جداگانه برای هرکدام
# (که تقریبا همه‌شان لیست + فرم ساده‌ی افزودن/ویرایش هستند)، یک موتور عمومی در
# views_lookup.py این تنظیمات را می‌خواند و صفحات را می‌سازد.

from . import forms as f
from locations.models import Country, Province, City, DestinationCity, Port
from rates.models import CargoType, CargoSubCategory, CargoSubCategoryChild
from documents.models import DocumentType
from support.models import SupportDepartment, TicketTopic, SupportAgent
from forwarders.models import ForwarderRole


class LookupConfig:
    def __init__(
        self,
        key,
        model,
        form_class,
        title,
        columns,
        search_fields=(),
        order_by="-id",
        has_is_active=True,
        select_related=(),
    ):
        self.key = key
        self.model = model
        self.form_class = form_class
        self.title = title
        self.columns = columns  # [(attr_path, header_label), ...]
        self.search_fields = search_fields
        self.order_by = order_by
        self.has_is_active = has_is_active
        self.select_related = select_related

    @property
    def list_url(self):
        return f"staff_dashboard:lookup_list"

    def base_queryset(self):
        qs = self.model.objects.all()
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        return qs.order_by(self.order_by)


LOOKUPS = {
    "countries": LookupConfig(
        key="countries",
        model=Country,
        form_class=f.CountryForm,
        title="کشورها",
        columns=[("name", "نام"), ("code", "کد")],
        search_fields=["name", "code"],
        order_by="name",
    ),
    "provinces": LookupConfig(
        key="provinces",
        model=Province,
        form_class=f.ProvinceForm,
        title="استان‌ها",
        columns=[("name", "نام"), ("country.name", "کشور")],
        search_fields=["name"],
        order_by="name",
        select_related=["country"],
    ),
    "cities": LookupConfig(
        key="cities",
        model=City,
        form_class=f.CityForm,
        title="شهرها",
        columns=[("name", "نام"), ("province.name", "استان")],
        search_fields=["name", "province__name"],
        order_by="name",
        select_related=["province"],
    ),
    "destination-cities": LookupConfig(
        key="destination-cities",
        model=DestinationCity,
        form_class=f.DestinationCityForm,
        title="شهرهای مقصد (بین‌المللی)",
        columns=[("name", "نام"), ("country.name", "کشور")],
        search_fields=["name", "country__name"],
        order_by="name",
        select_related=["country"],
    ),
    "ports": LookupConfig(
        key="ports",
        model=Port,
        form_class=f.PortForm,
        title="بنادر / فرودگاه‌ها / گمرک‌ها",
        columns=[("name", "نام"), ("get_port_type_display", "نوع"), ("city.name", "شهر"), ("code", "کد")],
        search_fields=["name", "code", "city__name"],
        order_by="name",
        select_related=["city"],
    ),
    "cargo-types": LookupConfig(
        key="cargo-types",
        model=CargoType,
        form_class=f.CargoTypeForm,
        title="انواع کالا (دسته اصلی)",
        columns=[("name", "نام"), ("get_transport_mode_display", "روش حمل")],
        search_fields=["name"],
        order_by="name",
        has_is_active=False,
    ),
    "cargo-subcategories": LookupConfig(
        key="cargo-subcategories",
        model=CargoSubCategory,
        form_class=f.CargoSubCategoryForm,
        title="زیردسته‌های کالا",
        columns=[("name", "نام"), ("category.name", "دسته اصلی")],
        search_fields=["name", "category__name"],
        order_by="name",
        has_is_active=False,
        select_related=["category"],
    ),
    "cargo-subcategory-children": LookupConfig(
        key="cargo-subcategory-children",
        model=CargoSubCategoryChild,
        form_class=f.CargoSubCategoryChildForm,
        title="زیرمجموعه‌های زیردسته کالا",
        columns=[("name", "نام"), ("subcategory.name", "زیردسته")],
        search_fields=["name", "subcategory__name"],
        order_by="name",
        has_is_active=False,
        select_related=["subcategory"],
    ),
    "document-types": LookupConfig(
        key="document-types",
        model=DocumentType,
        form_class=f.DocumentTypeForm,
        title="انواع مدرک",
        columns=[("title", "عنوان"), ("code", "کد"), ("allowed_extensions", "فرمت‌های مجاز")],
        search_fields=["title", "code"],
        order_by="title",
    ),
    "support-departments": LookupConfig(
        key="support-departments",
        model=SupportDepartment,
        form_class=f.SupportDepartmentForm,
        title="دپارتمان‌های پشتیبانی",
        columns=[("name", "نام"), ("get_panel_type_display", "نوع پنل")],
        search_fields=["name"],
        order_by="name",
    ),
    "ticket-topics": LookupConfig(
        key="ticket-topics",
        model=TicketTopic,
        form_class=f.TicketTopicForm,
        title="موضوعات تیکت",
        columns=[("title", "عنوان"), ("department.name", "دپارتمان")],
        search_fields=["title"],
        order_by="title",
        select_related=["department"],
    ),
    "support-agents": LookupConfig(
        key="support-agents",
        model=SupportAgent,
        form_class=f.SupportAgentForm,
        title="کارشناسان پشتیبانی",
        columns=[("user.mobile", "موبایل"), ("is_supervisor", "سرپرست؟")],
        search_fields=["user__mobile", "user__first_name", "user__last_name"],
        order_by="id",
        select_related=["user"],
    ),
    "forwarder-roles": LookupConfig(
        key="forwarder-roles",
        model=ForwarderRole,
        form_class=f.ForwarderRoleForm,
        title="نقش‌های فورواردر",
        columns=[("name", "نام نقش"), ("company.company_name", "شرکت")],
        search_fields=["name", "company__company_name"],
        order_by="company__company_name",
        has_is_active=False,
        select_related=["company"],
    ),
}
