# admin_dashboard/views_import.py
#
# ایمپورت اکسل یکپارچه برای سه محل قبلی که در پنل ادمین جنگو جداگانه و با
# کد تقریبا تکراری پیاده شده بودند (rates.CargoTypeAdmin،
# locations.ProvinceAdmin، locations.CountryAdmin). دو باگ واقعی هم که در
# بررسی کد قدیمی پیدا شد اینجا رفع شده‌اند:
#   ۱. ایمپورت استان country را ست نمی‌کرد (فیلد اجباری) -> اینجا به ایران
#      نسبت داده می‌شود (چون همه‌ی ۳۱ استان موجود، استان‌های ایران هستند).
#   ۲. ایمپورت کشور/پورت، نوع پورت ناشناخته را بی‌صدا «بندر دریایی» فرض
#      می‌کرد -> اینجا آن ردیف رد شده و به کاربر هشدار داده می‌شود.

import openpyxl
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from locations.models import Country, Province, City, DestinationCity, Port
from rates.models import CargoType, CargoSubCategory, TransportMode

from .decorators import platform_staff_required


class ExcelImportForm(forms.Form):
    excel_file = forms.FileField(label="فایل اکسل")


TRANSPORT_MODE_MAP = {
    'هوایی': TransportMode.AIR,
    'air': TransportMode.AIR,
    'دریایی fcl': TransportMode.SEA_FCL,
    'sea_fcl': TransportMode.SEA_FCL,
    'دریایی lcl': TransportMode.SEA_LCL,
    'sea_lcl': TransportMode.SEA_LCL,
    'زمینی': TransportMode.LAND,
    'land': TransportMode.LAND,
    'ریلی': TransportMode.RAIL,
    'rail': TransportMode.RAIL,
}

PORT_TYPE_MAP = {
    "بندر": Port.PortType.SEA,
    "sea": Port.PortType.SEA,
    "فرودگاه": Port.PortType.AIR,
    "air": Port.PortType.AIR,
    "گمرک زمینی": Port.PortType.land,
    "land": Port.PortType.land,
    "گمرک ریلی": Port.PortType.rail,
    "rail": Port.PortType.rail,
}


def _run_import(request, template_title, redirect_to, row_processor):
    if request.method == "POST":
        form = ExcelImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                wb = openpyxl.load_workbook(request.FILES["excel_file"], data_only=True)
                sheet = wb.active
                count = 0
                warnings = []
                for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                    result = row_processor(row)
                    if result == "ok":
                        count += 1
                    elif result:
                        warnings.append(f"ردیف {row_num}: {result}")

                messages.success(request, f"{count} ردیف با موفقیت ثبت/بروزرسانی شد.")
                if warnings:
                    shown = "؛ ".join(warnings[:10])
                    if len(warnings) > 10:
                        shown += f" ... و {len(warnings) - 10} مورد دیگر"
                    messages.warning(request, shown)
                return redirect_to()
            except Exception as e:
                messages.error(request, f"خطا در پردازش فایل: {e}")
    else:
        form = ExcelImportForm()

    return render(request, "admin_dashboard/excel_import.html", {"form": form, "title": template_title})


def _process_cargo_row(row):
    t_mode_raw = str(row[0]).strip().lower() if row[0] else None
    category_name = str(row[1]).strip() if len(row) > 1 and row[1] else None
    subcategory_name = str(row[2]).strip() if len(row) > 2 and row[2] else None
    description = str(row[3]).strip() if len(row) > 3 and row[3] else ""

    if not (t_mode_raw and category_name and subcategory_name):
        return None

    t_mode = TRANSPORT_MODE_MAP.get(t_mode_raw)
    if not t_mode:
        return f"روش حمل «{row[0]}» شناخته‌شده نیست."

    category_obj, _ = CargoType.objects.get_or_create(name=category_name, transport_mode=t_mode)
    CargoSubCategory.objects.update_or_create(
        category=category_obj, name=subcategory_name, defaults={"description": description}
    )
    return "ok"


def _get_or_create_iran():
    return Country.objects.get_or_create(code="IRN", defaults={"name": "ایران"})[0]


def _process_province_row(row, iran):
    province_name = str(row[0]).strip() if row[0] else None
    city_name = str(row[1]).strip() if len(row) > 1 and row[1] else None

    if not (province_name and city_name):
        return None

    province_obj, _ = Province.objects.get_or_create(name=province_name, defaults={"country": iran})
    City.objects.get_or_create(province=province_obj, name=city_name)
    return "ok"


def _process_country_row(row):
    country_name = str(row[0]).strip() if row[0] else None
    country_code = str(row[1]).strip()[:3] if len(row) > 1 and row[1] else None
    city_name = str(row[2]).strip() if len(row) > 2 and row[2] else None
    port_type_raw = str(row[3]).strip() if len(row) > 3 and row[3] else None
    port_name = str(row[4]).strip() if len(row) > 4 and row[4] else None
    port_code = str(row[5]).strip() if len(row) > 5 and row[5] else ""

    if not (country_name and country_code and city_name and port_name and port_type_raw):
        return None

    p_type = PORT_TYPE_MAP.get(port_type_raw.lower())
    if not p_type:
        return f"نوع پورت «{port_type_raw}» برای «{port_name}» شناخته‌شده نیست؛ این ردیف رد شد."

    country_obj, _ = Country.objects.get_or_create(name=country_name, defaults={"code": country_code})
    city_obj, _ = DestinationCity.objects.get_or_create(country=country_obj, name=city_name)
    Port.objects.get_or_create(city=city_obj, name=port_name, defaults={"port_type": p_type, "code": port_code})
    return "ok"


@login_required
@platform_staff_required
def import_cargo_types(request):
    return _run_import(
        request,
        "ایمپورت اکسل انواع کالا (ستون‌ها: روش حمل، دسته، زیردسته، توضیح اختیاری)",
        lambda: redirect("staff_dashboard:cargo_type_hub"),
        _process_cargo_row,
    )


@login_required
@platform_staff_required
def import_provinces(request):
    iran = _get_or_create_iran()
    return _run_import(
        request,
        "ایمپورت اکسل استان و شهر (ستون‌ها: استان، شهر)",
        lambda: redirect("staff_dashboard:lookup_list", key="provinces"),
        lambda row: _process_province_row(row, iran),
    )


@login_required
@platform_staff_required
def import_countries(request):
    return _run_import(
        request,
        "ایمپورت اکسل کشور/شهر مقصد/پورت (ستون‌ها: کشور، کد کشور، شهر، نوع پورت، نام پورت، کد پورت اختیاری)",
        lambda: redirect("staff_dashboard:lookup_list", key="countries"),
        _process_country_row,
    )
