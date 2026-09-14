import io
import json
import logging
from decimal import Decimal, InvalidOperation

import pandas as pd
import xlsxwriter
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView

from accounts.models import User
from locations.models import City, Country, DestinationCity, Port, Province
from rates.models import CargoType, ContainerSize, ContainerType, PricingUnit, Rate, RateTier, TransportMode

from .decorators import forwarder_required, get_company_for_user, staff_perm, staff_permission_required
from .forms import RateForm, RateTierFormSet

logger = logging.getLogger(__name__)


@login_required
@forwarder_required
@staff_permission_required('can_create_rates')
def rate_create_view(request):
    # دریافت لیست پورت‌ها برای فیلتر داینامیک در فرانت‌اند
    ports_data = list(Port.objects.values('id', 'name', 'port_type'))
    ports_json = json.dumps(ports_data)

    if request.method == 'POST':
        form = RateForm(request.POST)

        # ۱. مقداردهی مالک نرخ قبل از اعتبارسنجی (is_valid) تا خطای مدل رخ ندهد
        form.instance.forwarder = get_company_for_user(request.user)

        # ۲. پاس دادن instance فرم اصلی به فرم‌ست
        formset = RateTierFormSet(request.POST, instance=form.instance)

        if form.is_valid() and formset.is_valid():
            # ۳. ذخیره مستقیم (دیگر نیازی به commit=False نیست)
            form.save()
            formset.save()

            messages.success(request, "نرخ با موفقیت ذخیره شد.")
            return redirect('forwarder_panel:rate_list')
    else:
        form = RateForm()
        formset = RateTierFormSet()

    return render(request, 'forwarder_panel/rate_form.html', {
        'form': form,
        'formset': formset,
        'ports_json': ports_json
    })


@login_required
@forwarder_required
@staff_permission_required('can_view_rates')
def rate_list_view(request):
    forwarder_company = get_company_for_user(request.user)

    if forwarder_company:
        rates = Rate.objects.filter(forwarder=forwarder_company).select_related(
            'destination_country', 'destination_city', 'destination_port'
        ).prefetch_related('cargo_types').order_by('-created_at')

        # دریافت مقادیر فیلتر از URL
        country_id = request.GET.get('country')
        city_id = request.GET.get('city')
        mode = request.GET.get('mode')
        cargo_id = request.GET.get('cargo')
        status = request.GET.get('status')

        # اعمال فیلترها
        if country_id:
            rates = rates.filter(destination_country_id=country_id)
        if city_id:
            rates = rates.filter(destination_city_id=city_id)
        if mode:
            rates = rates.filter(transport_mode=mode)
        if cargo_id:
            rates = rates.filter(cargo_types__id=cargo_id)
        if status in ['active', 'inactive']:
            rates = rates.filter(is_active=(status == 'active'))

        # استخراج داده‌های یکتا برای پر کردن دراپ‌داون‌های فیلتر
        filter_countries = Rate.objects.filter(forwarder=forwarder_company, destination_country__isnull=False).values('destination_country__id', 'destination_country__name').distinct()
        filter_cities = Rate.objects.filter(forwarder=forwarder_company, destination_city__isnull=False).values('destination_city__id', 'destination_city__name').distinct()
        filter_cargos = CargoType.objects.filter(rates__forwarder=forwarder_company).distinct()

        # دریافت نام‌های نمایشی روش‌های حمل
        transport_modes = []
        mode_choices = dict(Rate._meta.get_field('transport_mode').choices)
        used_modes = Rate.objects.filter(forwarder=forwarder_company).values_list('transport_mode', flat=True).distinct()
        for m in used_modes:
            if m in mode_choices:
                transport_modes.append({'id': m, 'name': mode_choices[m]})

    else:
        rates = []
        filter_countries = filter_cities = filter_cargos = transport_modes = []

    paginator = Paginator(rates, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    context = {
        'rates': page_obj,
        'page_obj': page_obj,
        'querystring': querystring + '&' if querystring else '',
        'filter_countries': filter_countries,
        'filter_cities': filter_cities,
        'filter_cargos': filter_cargos,
        'transport_modes': transport_modes,
    }
    return render(request, 'forwarder_panel/rate_list.html', context)


@login_required
@forwarder_required
@staff_permission_required('can_edit_rates')
@require_POST
def toggle_rate_status(request, rate_id):
    rate = get_object_or_404(Rate, id=rate_id, forwarder=get_company_for_user(request.user))

    try:
        data = json.loads(request.body)
        is_active = data.get('is_active', False)

        rate.is_active = is_active
        rate.save()

        return JsonResponse({'success': True, 'is_active': rate.is_active})
    except Exception:
        logger.exception("خطا در تغییر وضعیت نرخ %s", rate_id)
        return JsonResponse({'success': False, 'error': 'خطایی رخ داد. لطفاً دوباره تلاش کنید.'}, status=400)


@login_required
@forwarder_required
@staff_permission_required('can_delete_rates')
@require_POST
def delete_rate(request, rate_id):
    rate = get_object_or_404(Rate, id=rate_id, forwarder=get_company_for_user(request.user))

    try:
        rate.delete()
        return JsonResponse({'success': True})
    except Exception:
        logger.exception("خطا در حذف نرخ %s", rate_id)
        return JsonResponse({'success': False, 'error': 'خطایی رخ داد. لطفاً دوباره تلاش کنید.'}, status=400)


class RateDetailUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Rate
    form_class = RateForm
    template_name = 'forwarder_panel/rate_detail.html'
    success_url = reverse_lazy('forwarder_panel:rate_list')

    def test_func(self):
        user = self.request.user
        allowed_roles = [
            User.Role.FORWARDER_ADMIN,
            User.Role.FORWARDER_EXPERT,
            User.Role.FORWARDER_FINANCE,
        ]
        if user.role not in allowed_roles:
            return False
        if not staff_perm(user, 'can_edit_rates'):
            return False
        company = get_company_for_user(user)
        if not company:
            return False
        return company.is_verified and company.is_active


    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            if self.request.user.role == User.Role.FORWARDER_ADMIN:
                messages.warning(self.request, "برای استفاده از این بخش، ابتدا مدارک شرکت باید تایید شود.")
                return redirect("forwarder_panel:documents")
            return HttpResponseForbidden("شما دسترسی مشاهده این صفحه را ندارید.")
        return super().handle_no_permission()


    def get_queryset(self):
        forwarder_company = get_company_for_user(self.request.user)
        if forwarder_company:
            return Rate.objects.filter(forwarder=forwarder_company)
        return Rate.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ports_data = list(Port.objects.values('id', 'name', 'port_type'))
        context['ports_json'] = json.dumps(ports_data)

        if self.request.POST:
            context['formset'] = RateTierFormSet(self.request.POST, instance=self.object)
        else:
            context['formset'] = RateTierFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        with transaction.atomic():
            self.object = form.save()

            if formset.is_valid():
                formset.instance = self.object
                formset.save()
            else:
                return self.render_to_response(self.get_context_data(form=form))

        messages.success(self.request, "تغییرات با موفقیت ذخیره شد.")
        return super().form_valid(form)


@login_required
@forwarder_required
@staff_permission_required('can_delete_rates')
@require_POST
def rate_bulk_delete(request):
    try:
        data = json.loads(request.body)
        ids = data.get('ids', [])

        if not ids:
            return JsonResponse({'success': False, 'error': 'لیست شناسه‌ها خالی است.'}, status=400)

        forwarder_company = get_company_for_user(request.user)

        if forwarder_company:
            Rate.objects.filter(id__in=ids, forwarder=forwarder_company).delete()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'دسترسی غیرمجاز'}, status=403)

    except Exception:
        logger.exception("خطا در حذف گروهی نرخ‌ها")
        return JsonResponse({'success': False, 'error': 'خطایی رخ داد. لطفاً دوباره تلاش کنید.'}, status=400)


@login_required
@forwarder_required
@staff_permission_required('can_bulk_upload_rates')
def download_rate_template_excel(request):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})

    ws_data = workbook.add_worksheet('فرم ورود نرخ‌ها')
    ws_source = workbook.add_worksheet('DataSources')

    # لیست‌های dropdown از داده‌های واقعی پایگاه‌داده ساخته می‌شوند (نه
    # مقادیر ثابت نمونه) تا هر مقداری که کاربر از این فایل انتخاب می‌کند،
    # در upload_rate_excel قابل تطبیق با رکورد واقعی باشد.
    shipping_methods = [label for _, label in TransportMode.choices]
    provinces = list(Province.objects.filter(is_active=True).order_by('name').values_list('name', flat=True))
    origin_cities = list(City.objects.filter(is_active=True).order_by('name').values_list('name', flat=True))
    countries = list(Country.objects.filter(is_active=True).order_by('name').values_list('name', flat=True))
    destination_cities = list(DestinationCity.objects.filter(is_active=True).order_by('name').values_list('name', flat=True))
    ports = list(Port.objects.filter(is_active=True).order_by('name').values_list('name', flat=True))
    cargo_types = list(CargoType.objects.order_by('name').values_list('name', flat=True))
    container_sizes = [label for _, label in ContainerSize.choices]
    container_types = [label for _, label in ContainerType.choices]
    pricing_units = [label for _, label in PricingUnit.choices]

    sources = [
        ('A', shipping_methods), ('B', provinces), ('C', origin_cities),
        ('D', countries), ('E', destination_cities), ('F', ports), ('G', cargo_types),
        ('H', container_sizes), ('I', container_types), ('J', pricing_units)
    ]

    for col_letter, data_list in sources:
        for row_num, item in enumerate(data_list):
            ws_source.write(f'{col_letter}{row_num + 1}', str(item))

    headers = [
        'روش حمل', 'استان مبدا', 'شهر مبدا', 'کشور مقصد', 'شهر مقصد',
        'پورت مقصد', 'نوع کالا', 'اعتبار تا (YYYY-MM-DD)', 'از وزن', 'تا وزن',
        'سایز کانتینر', 'نوع کانتینر', 'واحد قیمت‌گذاری', 'مبلغ'
    ]

    header_format = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})

    for col_num, header in enumerate(headers):
        ws_data.write(0, col_num, header, header_format)
        ws_data.set_column(col_num, col_num, 15)

    max_rows = 500

    validations = {
        0:  ('A', len(shipping_methods)),
        1:  ('B', len(provinces)),
        2:  ('C', len(origin_cities)),
        3:  ('D', len(countries)),
        4:  ('E', len(destination_cities)),
        5:  ('F', len(ports)),
        6:  ('G', len(cargo_types)),
        10: ('H', len(container_sizes)),
        11: ('I', len(container_types)),
        12: ('J', len(pricing_units)),
    }

    for col_index, (source_col, items_count) in validations.items():
        if items_count > 0:
            ws_data.data_validation(1, col_index, max_rows, col_index, {
                'validate': 'list',
                'source': f'=DataSources!${source_col}$1:${source_col}${items_count}'
            })

    workbook.close()

    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Bulk_Rate_Template.xlsx"'
    return response


def _excel_cell_str(row, column):
    """مقدار یک سلول را به رشته‌ی trim‌شده تبدیل می‌کند؛ خانه‌ی خالی → None."""
    value = row.get(column)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value).strip()


def _excel_cell_decimal(row, column):
    """مقدار یک سلول عددی را به Decimal تبدیل می‌کند؛ خانه‌ی خالی → None."""
    raw = row.get(column)
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        raise ValueError(f"مقدار «{raw}» یک عدد معتبر نیست.")


def _build_rate_from_excel_row(row, forwarder_company):
    """
    یک ردیف از فایل اکسل بارگذاری‌شده را به یک Rate + RateTier تبدیل و
    ذخیره می‌کند. هر ردیف مستقل است (یک نرخ با دقیقاً یک ردیف قیمتی)،
    چون تمام ستون‌های سطح نرخ (روش حمل، مبدا/مقصد، نوع کالا، اعتبار) و
    سطح ردیف قیمتی (وزن/کانتینر، واحد قیمت، مبلغ) هر دو در همان ردیف اکسل
    هستند. خطاها به‌صورت ValueError/ValidationError بالا می‌روند تا
    فراخوان بتواند شماره ردیف را به پیام اضافه کند.
    """
    transport_mode_by_label = {label: value for value, label in TransportMode.choices}
    pricing_unit_by_label = {label: value for value, label in PricingUnit.choices}
    container_size_by_label = {label: value for value, label in ContainerSize.choices}
    container_type_by_label = {label: value for value, label in ContainerType.choices}

    transport_label = _excel_cell_str(row, 'روش حمل')
    transport_mode = transport_mode_by_label.get(transport_label)
    if not transport_mode:
        raise ValueError(f"روش حمل «{transport_label}» معتبر نیست.")

    origin_province_name = _excel_cell_str(row, 'استان مبدا')
    origin_province = Province.objects.filter(name=origin_province_name, is_active=True).first()
    if not origin_province:
        raise ValueError(f"استان مبدا «{origin_province_name}» یافت نشد.")

    origin_city_name = _excel_cell_str(row, 'شهر مبدا')
    origin_city = City.objects.filter(
        name=origin_city_name, province=origin_province, is_active=True,
    ).first()
    if not origin_city:
        raise ValueError(f"شهر مبدا «{origin_city_name}» در استان «{origin_province_name}» یافت نشد.")

    destination_country_name = _excel_cell_str(row, 'کشور مقصد')
    destination_country = Country.objects.filter(name=destination_country_name, is_active=True).first()
    if not destination_country:
        raise ValueError(f"کشور مقصد «{destination_country_name}» یافت نشد.")

    destination_city_name = _excel_cell_str(row, 'شهر مقصد')
    destination_city = DestinationCity.objects.filter(
        name=destination_city_name, country=destination_country, is_active=True,
    ).first()
    if not destination_city:
        raise ValueError(f"شهر مقصد «{destination_city_name}» در کشور «{destination_country_name}» یافت نشد.")

    destination_port_name = _excel_cell_str(row, 'پورت مقصد')
    destination_port = Port.objects.filter(
        name=destination_port_name, city=destination_city, is_active=True,
    ).first()
    if not destination_port:
        raise ValueError(f"پورت مقصد «{destination_port_name}» در شهر «{destination_city_name}» یافت نشد.")

    cargo_type_name = _excel_cell_str(row, 'نوع کالا')
    cargo_type = CargoType.objects.filter(name=cargo_type_name).first()
    if not cargo_type:
        raise ValueError(f"نوع کالا «{cargo_type_name}» یافت نشد.")

    valid_until_raw = row.get('اعتبار تا (YYYY-MM-DD)')
    if valid_until_raw is None or (isinstance(valid_until_raw, float) and pd.isna(valid_until_raw)):
        raise ValueError("تاریخ اعتبار الزامی است.")
    try:
        valid_until = pd.to_datetime(valid_until_raw).date()
    except (ValueError, TypeError):
        raise ValueError(f"تاریخ اعتبار «{valid_until_raw}» معتبر نیست (فرمت مورد انتظار: YYYY-MM-DD).")

    pricing_unit_label = _excel_cell_str(row, 'واحد قیمت‌گذاری')
    pricing_unit = pricing_unit_by_label.get(pricing_unit_label)
    if not pricing_unit:
        raise ValueError(f"واحد قیمت‌گذاری «{pricing_unit_label}» معتبر نیست.")

    amount = _excel_cell_decimal(row, 'مبلغ')
    if amount is None:
        raise ValueError("مبلغ الزامی است.")

    weight_from = _excel_cell_decimal(row, 'از وزن')
    weight_to = _excel_cell_decimal(row, 'تا وزن')

    container_size_label = _excel_cell_str(row, 'سایز کانتینر')
    container_type_label = _excel_cell_str(row, 'نوع کانتینر')
    container_size = container_size_by_label.get(container_size_label) if container_size_label else None
    container_type = container_type_by_label.get(container_type_label) if container_type_label else None

    with transaction.atomic():
        rate = Rate(
            forwarder=forwarder_company,
            transport_mode=transport_mode,
            origin_province=origin_province,
            origin_city=origin_city,
            destination_country=destination_country,
            destination_city=destination_city,
            destination_port=destination_port,
            valid_until=valid_until,
        )
        rate.full_clean()
        rate.save()
        rate.cargo_types.add(cargo_type)

        tier = RateTier(
            rate=rate,
            pricing_unit=pricing_unit,
            price=amount,
            weight_from=weight_from,
            weight_to=weight_to,
            container_size=container_size,
            container_type=container_type,
        )
        tier.full_clean()
        tier.save()


@login_required
@forwarder_required
@staff_permission_required('can_bulk_upload_rates')
def upload_rate_excel(request):
    if request.method != 'POST':
        return redirect('forwarder_panel:rate_list')

    excel_file = request.FILES.get('excel_file')
    if not excel_file:
        messages.error(request, 'لطفاً یک فایل انتخاب کنید.')
        return redirect('forwarder_panel:rate_list')

    forwarder_company = get_company_for_user(request.user)
    if not forwarder_company:
        messages.error(request, 'شرکت فورواردر یافت نشد.')
        return redirect('forwarder_panel:rate_list')

    try:
        df = pd.read_excel(excel_file, sheet_name='فرم ورود نرخ‌ها')
        df = df.dropna(how='all')
    except Exception as e:
        messages.error(request, f'خطا در خواندن فایل: {str(e)}')
        return redirect('forwarder_panel:rate_list')

    created_count = 0
    row_errors = []

    for index, row in df.iterrows():
        row_num = index + 2  # ردیف ۱ هدر است؛ index از ۰ شروع می‌شود
        try:
            _build_rate_from_excel_row(row, forwarder_company)
            created_count += 1
        except ValidationError as e:
            detail = '; '.join(e.messages) if hasattr(e, 'messages') else str(e)
            row_errors.append(f"ردیف {row_num}: {detail}")
        except ValueError as e:
            row_errors.append(f"ردیف {row_num}: {e}")
        except Exception:
            logger.exception("خطای غیرمنتظره در پردازش ردیف %s فایل بارگذاری نرخ", row_num)
            row_errors.append(f"ردیف {row_num}: خطای غیرمنتظره در پردازش این ردیف.")

    if created_count:
        messages.success(request, f"{created_count} نرخ با موفقیت ایجاد شد.")

    if row_errors:
        shown = row_errors[:10]
        remaining = len(row_errors) - len(shown)
        error_text = " | ".join(shown)
        if remaining > 0:
            error_text += f" | (و {remaining} خطای دیگر)"
        messages.error(request, f"برخی ردیف‌ها ذخیره نشدند: {error_text}")

    if not created_count and not row_errors:
        messages.warning(request, "هیچ ردیف معتبری در فایل یافت نشد.")

    return redirect('forwarder_panel:rate_list')
