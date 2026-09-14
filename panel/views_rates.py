import io
import json
import logging

import pandas as pd
import xlsxwriter
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView

from accounts.models import User
from locations.models import Port
from rates.models import CargoType, Rate

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

    shipping_methods = ['دریایی', 'هوایی', 'زمینی', 'ریلی']
    provinces = ['تهران', 'هرمزگان', 'آذربایجان غربی', 'خراسان رضوی']
    countries = ['ایران', 'امارات', 'آلمان', 'ترکیه', 'چین']
    cities = ['تهران', 'بندرعباس', 'دبی', 'فرانکفورت', 'استانبول', 'شانگهای']
    ports = ['جبل علی', 'بندر شهید رجایی', 'هامبورگ']
    cargo_types = ['عمومی', 'خطرناک', 'فاسدشدنی', 'دارویی']
    container_sizes = ['20ft', '40ft']
    container_types = ['Standard', 'High Cube', 'Reefer', 'Open Top']
    pricing_units = ['کانتینر', 'کیلوگرم', 'CBM', 'ماشین کامل']

    sources = [
        ('A', shipping_methods), ('B', provinces), ('C', cities),
        ('D', countries), ('E', ports), ('F', cargo_types),
        ('G', container_sizes), ('H', container_types), ('I', pricing_units)
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
        2:  ('C', len(cities)),
        3:  ('D', len(countries)),
        4:  ('C', len(cities)),
        5:  ('E', len(ports)),
        6:  ('F', len(cargo_types)),
        10: ('G', len(container_sizes)),
        11: ('H', len(container_types)),
        12: ('I', len(pricing_units)),
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


@login_required
@forwarder_required
@staff_permission_required('can_bulk_upload_rates')
def upload_rate_excel(request):
    if request.method == 'POST':
        excel_file = request.FILES.get('excel_file')

        if not excel_file:
            messages.error(request, 'لطفاً یک فایل انتخاب کنید.')
            return redirect('forwarder_panel:rate_list')

        try:
            df = pd.read_excel(excel_file, sheet_name='فرم ورود نرخ‌ها')
            df = df.dropna(how='all')

            for index, row in df.iterrows():
                shipping_method = row.get('روش حمل')
                origin_province = row.get('استان مبدا')
                amount = row.get('مبلغ')

            messages.success(request, 'نرخ‌ها با موفقیت بارگذاری شدند.')

        except Exception as e:
            messages.error(request, f'خطا در پردازش فایل: {str(e)}')

        return redirect('forwarder_panel:rate_list')
