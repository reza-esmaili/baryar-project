from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import RateForm, RateTierFormSet, StaffForm, BranchForm, ForwarderDocumentsForm
from accounts.models import User, IdentityDocument
from forwarders.models import ForwarderBranch, ForwarderStaff, ForwarderCompany, ForwarderRole

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from locations.models import Port, City
import json
from rates.models import Rate, CargoType
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView
from django.urls import reverse_lazy
from django.db import transaction
import io
import xlsxwriter
import pandas as pd
from django.db.models import Q
from orders.models import CargoRequest, OrderStatus, OrderHistory, OrderMessage, CustomerNotification, ForwarderNotification
from documents.models import OrderDocument, AdditionalDocumentRequest

from django.db.models import Sum, Count, Avg
from django.utils import timezone
from datetime import timedelta
from rates.models import TransportMode
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, TruncQuarter, TruncYear
import jdatetime
# ایمپورت‌های اضافه شده برای سطح دسترسی
from .decorators import forwarder_required, get_company_for_user, staff_perm, staff_permission_required
def get_forwarder_verification_status(user):
    """
    خروجی:
    - no_company: هنوز اطلاعات شرکت ثبت نشده
    - pending: شرکت ثبت شده ولی تایید نشده
    - verified: شرکت تایید شده
    - not_forwarder_admin: کاربر ادمین فورواردر نیست
    """
    if not user.is_authenticated or user.role != User.Role.FORWARDER_ADMIN:
        return "not_forwarder_admin", None

    try:
        company = user.forwarder_company
    except ForwarderCompany.DoesNotExist:
        return "no_company", None

    if company.is_verified and company.is_active:
        return "verified", company

    return "pending", company

@login_required
@forwarder_required
def documents_view(request):
    """
    صفحه مدارک و مستندات فورواردر.
    فورواردر بعد از ثبت‌نام اولیه وارد این صفحه می‌شود،
    اطلاعات شرکت و مدارک را ارسال می‌کند و تا تایید کارشناس
    اجازه استفاده از سایر بخش‌های پنل را ندارد.
    """
    user = request.user
    status, company = get_forwarder_verification_status(user)

    if status == "not_forwarder_admin":
        return HttpResponseForbidden("شما دسترسی مشاهده این صفحه را ندارید.")

    documents = IdentityDocument.objects.filter(user=user).order_by("-created_at")

    if request.method == "POST":
        form = ForwarderDocumentsForm(request.POST, request.FILES, user=user, company=company)

        if form.is_valid():
            with transaction.atomic():
                applicant_role = form.cleaned_data["applicant_role"]

                if applicant_role == ForwarderDocumentsForm.ApplicantRole.CEO:
                    ceo_first_name = user.first_name
                    ceo_last_name = user.last_name
                    ceo_mobile = user.mobile
                    ceo_national_code = form.cleaned_data["ceo_national_code"]
                else:
                    ceo_first_name = form.cleaned_data["ceo_first_name"]
                    ceo_last_name = form.cleaned_data["ceo_last_name"]
                    ceo_mobile = form.cleaned_data["ceo_mobile"]
                    ceo_national_code = form.cleaned_data["ceo_national_code"]

                company, created = ForwarderCompany.objects.update_or_create(
                    admin_user=user,
                    defaults={
                        "company_name": form.cleaned_data["company_name"],
                        "company_type": form.cleaned_data["company_type"],
                        "national_id": form.cleaned_data["national_id"],
                        "registration_number": form.cleaned_data["registration_number"],
                        "ceo_first_name": ceo_first_name,
                        "ceo_last_name": ceo_last_name,
                        "ceo_national_code": ceo_national_code,
                        "phone": form.cleaned_data["phone"],
                        "email": form.cleaned_data["email"],
                        "postal_code": form.cleaned_data["postal_code"],
                        "address": form.cleaned_data["address"],

                        # مهم:
                        # بعد از ارسال مدارک، شرکت فعال عملیاتی نیست تا کارشناس تایید کند.
                        "is_verified": False,
                        "is_active": False,
                    },
                )

                uploaded_docs = {
                    "articles_of_association": IdentityDocument.DocType.ARTICLES_OF_ASSOCIATION,
                    "establishment_notice": IdentityDocument.DocType.ESTABLISHMENT_NOTICE,
                    "latest_changes": IdentityDocument.DocType.LATEST_CHANGES,
                    "ceo_national_card": IdentityDocument.DocType.CEO_NATIONAL_CARD,
                }

                for file_field, doc_type in uploaded_docs.items():
                    uploaded_file = request.FILES.get(file_field)
                    if uploaded_file:
                        # اگر کاربر دوباره مدارک را ارسال کرد، مدرک قبلی از همان نوع رد/آرشیو منطقی ندارد
                        # اما برای سادگی، مدرک جدید ساخته می‌شود و مدارک قبلی باقی می‌مانند.
                        IdentityDocument.objects.create(
                            user=user,
                            doc_type=doc_type,
                            company=company,
                            file=uploaded_file,
                            status=IdentityDocument.Status.PENDING,
                        )

                messages.success(
                    request,
                    "اطلاعات و مدارک شما با موفقیت ثبت شد و در انتظار بررسی کارشناس قرار گرفت."
                )
                return redirect("forwarder_panel:documents")

        else:
            messages.error(request, "لطفاً خطاهای فرم را بررسی و اصلاح کنید.")

    else:
        form = ForwarderDocumentsForm(user=user, company=company)

    status, company = get_forwarder_verification_status(user)

    context = {
        "form": form,
        "company": company,
        "documents": documents,
        "verification_status": status,
        "registered_user": user,
    }

    return render(request, "forwarder_panel/documents.html", context)


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

    context = {
        'rates': rates,
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
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@forwarder_required
@staff_permission_required('can_delete_rates')
@require_POST
def delete_rate(request, rate_id):
    rate = get_object_or_404(Rate, id=rate_id, forwarder=get_company_for_user(request.user))
    
    try:
        rate.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


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
@staff_permission_required('can_view_rates')
def load_cargo_types(request):
    transport_mode = request.GET.get('transport_mode')
    print(f"درخواست AJAX برای نوع کالا دریافت شد. روش حمل: {transport_mode}")
    cargo_types_list = list(CargoType.objects.filter(transport_mode=transport_mode).values('id', 'name'))
    print(f"نتیجه فیلتر: {cargo_types_list}")
    return JsonResponse(cargo_types_list, safe=False)


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
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


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


@login_required
@forwarder_required
@staff_permission_required('can_view_branches')
def branch_list_view(request):
    company = get_company_for_user(request.user)
    branches = ForwarderBranch.objects.filter(company=company).order_by('-created_at')
    return render(request, 'forwarder_panel/branch_list.html', {'branches': branches})


@login_required
@forwarder_required
@staff_permission_required('can_manage_branches')
def branch_create_view(request):
    company = get_company_for_user(request.user)
    if request.method == 'POST':
        form = BranchForm(request.POST)
        if form.is_valid():
            form.save(forwarder_company=company)
            messages.success(request, "شعبه با موفقیت افزوده شد.")
            return redirect('forwarder_panel:branch_list')
    else:
        form = BranchForm()
    return render(request, 'forwarder_panel/branch_form.html', {'form': form})


@login_required
@forwarder_required
@staff_permission_required('can_manage_branches')
def branch_update_view(request, pk):
    company = get_company_for_user(request.user)
    branch = get_object_or_404(ForwarderBranch, pk=pk, company=company)
    
    if request.method == 'POST':
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            form.save(forwarder_company=company)
            messages.success(request, "تغییرات شعبه ذخیره شد.")
            return redirect('forwarder_panel:branch_list')
    else:
        form = BranchForm(instance=branch)
    return render(request, 'forwarder_panel/branch_form.html', {'form': form, 'branch': branch})


@login_required
@forwarder_required
@staff_permission_required('can_manage_branches')
@require_POST
def toggle_branch_status(request, pk):
    company = get_company_for_user(request.user)
    branch = get_object_or_404(ForwarderBranch, pk=pk, company=company)
    data = json.loads(request.body)
    branch.is_active = data.get('is_active', False)
    branch.save()
    return JsonResponse({'success': True, 'is_active': branch.is_active})


# --- بخش کارمندان (Staff) ---
@login_required
@forwarder_required
@staff_permission_required('can_view_staff')
def staff_list_view(request):
    company = get_company_for_user(request.user)
    staff = ForwarderStaff.objects.filter(company=company).select_related('user').order_by('-created_at')
    return render(request, 'forwarder_panel/staff_list.html', {'staff': staff})


@login_required
@forwarder_required
@staff_permission_required('can_manage_staff')
def staff_create_view(request):
    company = get_company_for_user(request.user)
    if request.method == 'POST':
        form = StaffForm(request.POST, forwarder_company=company)
        if form.is_valid():
            form.save(forwarder_company=company)
            messages.success(request, "کارمند با موفقیت افزوده شد.")
            return redirect('forwarder_panel:staff_list')
    else:
        form = StaffForm(forwarder_company=company)
    return render(request, 'forwarder_panel/staff_form.html', {'form': form, 'is_edit': False})


@login_required
@forwarder_required
@staff_permission_required('can_manage_staff')
def staff_edit_view(request, staff_id):
    company = get_company_for_user(request.user)
    staff_obj = get_object_or_404(ForwarderStaff, pk=staff_id, company=company)
    if request.method == 'POST':
        form = StaffForm(request.POST, forwarder_company=company, instance=staff_obj)
        if form.is_valid():
            form.save(forwarder_company=company)
            messages.success(request, "اطلاعات کارمند با موفقیت ویرایش شد.")
            return redirect('forwarder_panel:staff_list')
    else:
        form = StaffForm(forwarder_company=company, instance=staff_obj)
    return render(request, 'forwarder_panel/staff_form.html', {'form': form, 'is_edit': True, 'staff_obj': staff_obj})


@login_required
@forwarder_required
@staff_permission_required('can_manage_staff')
def staff_delete_view(request, staff_id):
    company = get_company_for_user(request.user)
    staff_obj = get_object_or_404(ForwarderStaff, pk=staff_id, company=company)
    if request.method == 'POST':
        user = staff_obj.user
        staff_obj.delete()
        user.is_active = False
        user.save(update_fields=['is_active'])
        messages.success(request, "کارمند با موفقیت حذف شد.")
    return redirect('forwarder_panel:staff_list')


@login_required
@forwarder_required
@staff_permission_required('can_manage_staff')
def staff_toggle_active_view(request, staff_id):
    company = get_company_for_user(request.user)
    staff_obj = get_object_or_404(ForwarderStaff, pk=staff_id, company=company)
    if request.method == 'POST':
        new_state = not staff_obj.is_active
        staff_obj.is_active = new_state
        staff_obj.save(update_fields=['is_active'])
        staff_obj.user.is_active = new_state
        staff_obj.user.save(update_fields=['is_active'])
        label = "فعال" if new_state else "غیرفعال"
        messages.success(request, f"حساب کارمند با موفقیت {label} شد.")
    return redirect('forwarder_panel:staff_list')


@login_required
def first_login_password_change(request):
    """تغییر اجباری رمز عبور در اولین ورود کارمند فورواردر"""
    from django.contrib.auth import update_session_auth_hash
    from accounts.models import OTPCode
    from accounts.services import request_otp, verify_otp

    user = request.user

    if not getattr(user, 'must_change_password', False):
        return redirect('forwarder_panel:dashboard')

    staff_profile = getattr(user, 'forwarder_staff', None)

    if request.method == 'POST':
        action = request.POST.get('action')

        # ─── مرحله ۱: تأیید کد ملی و ارسال OTP ───
        if action == 'send_otp':
            national_code = request.POST.get('national_code', '').strip()
            if not staff_profile or staff_profile.national_code != national_code:
                messages.error(request, "کد ملی وارد شده صحیح نیست.")
                return render(request, 'forwarder_panel/first_login_change_password.html', {'step': 1})
            try:
                request_otp(user.mobile, OTPCode.Purpose.PASSWORD_RESET)
                request.session['flcp_nc_ok'] = True
                messages.success(request, "کد تایید به شماره موبایل شما ارسال شد.")
            except ValueError as e:
                messages.error(request, str(e))
                return render(request, 'forwarder_panel/first_login_change_password.html', {'step': 1})
            return render(request, 'forwarder_panel/first_login_change_password.html', {'step': 2})

        # ─── مرحله ۲: تأیید OTP + تنظیم رمز جدید ───
        elif action == 'set_password':
            if not request.session.get('flcp_nc_ok'):
                return render(request, 'forwarder_panel/first_login_change_password.html', {'step': 1})

            otp_code = request.POST.get('otp_code', '').strip()
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')
            errors = {}

            if not verify_otp(user.mobile, OTPCode.Purpose.PASSWORD_RESET, otp_code):
                errors['otp_code'] = "کد تایید نامعتبر یا منقضی شده است."

            if len(new_password) < 8:
                errors['new_password'] = "رمز عبور باید حداقل ۸ کاراکتر باشد."
            elif new_password != confirm_password:
                errors['confirm_password'] = "رمز عبور و تکرار آن یکسان نیستند."

            if errors:
                return render(request, 'forwarder_panel/first_login_change_password.html',
                              {'step': 2, 'errors': errors})

            user.set_password(new_password)
            user.must_change_password = False
            user.save(update_fields=['password', 'must_change_password'])
            update_session_auth_hash(request, user)
            request.session.pop('flcp_nc_ok', None)
            messages.success(request, "رمز عبور با موفقیت تغییر یافت. خوش آمدید!")
            return redirect('forwarder_panel:dashboard')

    return render(request, 'forwarder_panel/first_login_change_password.html', {'step': 1})


@login_required
@forwarder_required
def load_cities(request):
    province_id = request.GET.get('province_id')
    if province_id:
        cities = City.objects.filter(province_id=province_id).order_by('name')
        city_list = list(cities.values('id', 'name'))
        return JsonResponse(city_list, safe=False)
    return JsonResponse([], safe=False)


# ==============================================================================
# مدیریت سفارشات فورواردر
# ==============================================================================
@login_required
@forwarder_required
@staff_permission_required('can_manage_orders')
def order_list_view(request):
    """
    نمایش لیست سفارشات مربوط به فورواردر، فیلترینگ و امکان تغییر وضعیت گروهی.
    """
    forwarder_company = get_company_for_user(request.user)
    
    # -------------------------------------------------------------------------
    # بخش اول: پردازش درخواست‌های POST برای تغییر وضعیت گروهی
    # -------------------------------------------------------------------------
    if request.method == 'POST':
        new_status = request.POST.get('bulk_status')
        selected_orders = request.POST.getlist('selected_orders')
        
        if new_status and selected_orders:
            try:
                # استفاده از atomic برای اطمینان از انجام کامل یا لغو کامل تراکنش‌ها
                with transaction.atomic():
                    # فیلتر ایمن: فقط سفارشاتی که متعلق به شرکت این کاربر هستند آپدیت شوند
                    orders_to_update = CargoRequest.objects.filter(
                        id__in=selected_orders, 
                        selected_rate__forwarder=forwarder_company
                    )
                    
                    updated_count = 0
                    for order in orders_to_update:
                        old_status = order.status
                        
                        # در صورتی که وضعیت جدید با وضعیت قبلی تفاوت داشت اعمال شود
                        if old_status != new_status:
                            order.status = new_status
                            order.save(update_fields=['status'])
                            
                            # ثبت لاگ دقیق در OrderHistory مشابه با order_detail_view
                            OrderHistory.objects.create(
                                order=order,
                                changed_by=request.user,
                                field_name='status',
                                old_value=old_status,
                                new_value=new_status,
                                note="تغییر وضعیت گروهی از لیست سفارشات"
                            )
                            updated_count += 1
                            
                messages.success(request, f"وضعیت {updated_count} سفارش با موفقیت به‌روزرسانی شد.")
            except Exception as e:
                messages.error(request, f"خطا در بروزرسانی گروهی سفارشات: {e}")
        else:
            messages.warning(request, "لطفاً حداقل یک سفارش و یک وضعیت جدید برای اعمال انتخاب کنید.")
            
        # جلوگیری از ارسال مجدد فرم هنگام رفرش صفحه
        return redirect('forwarder_panel:order_list')

    # -------------------------------------------------------------------------
    # بخش دوم: پردازش درخواست‌های GET برای جستجو، فیلتر و رندر صفحه
    # -------------------------------------------------------------------------
    if forwarder_company:
        # دریافت پایه سفارشاتی که متعلق به این فورواردر است و پیش‌نویس نیستند
        orders = CargoRequest.objects.filter(
            selected_rate__forwarder=forwarder_company
        ).exclude(status=OrderStatus.DRAFT).select_related(
            'customer', 'destination_port', 'origin_city', 'selected_rate', 'cargo_type'
        ).order_by('-created_at')
        
        # استخراج پارامترهای GET از URL
        search_query = request.GET.get('q', '')
        country_id = request.GET.get('country')
        city_id = request.GET.get('city')
        mode = request.GET.get('mode')
        status = request.GET.get('status')
        
        # اعمال فیلتر جستجو (با استفاده از OR های متوالی)
        if search_query:
            orders = orders.filter(
                Q(id__icontains=search_query) |
                Q(sender_name__icontains=search_query) |
                Q(sender_national_id__icontains=search_query) |
                Q(sender_phone__icontains=search_query) |
                Q(customer__mobile__icontains=search_query) |
                Q(customer__first_name__icontains=search_query) |
                Q(customer__last_name__icontains=search_query)
            )
            
        # اعمال فیلترهای دراپ‌داون
        if country_id:
            orders = orders.filter(destination_port__city__province__country_id=country_id)
        if city_id:
            orders = orders.filter(destination_port__city_id=city_id)
        if mode:
            orders = orders.filter(transport_mode=mode)
        if status:
            orders = orders.filter(status=status)

        # تهیه داده‌های لازم برای پر کردن فرم فیلترها (شهرهای دارای سفارش و وضعیت‌ها)
        city_ids = CargoRequest.objects.filter(
            selected_rate__forwarder=forwarder_company
        ).exclude(status=OrderStatus.DRAFT).values_list('destination_port__city_id', flat=True).distinct()
        
        filter_cities = City.objects.filter(id__in=city_ids)        
        transport_modes = [{'id': k, 'name': v} for k, v in CargoRequest._meta.get_field('transport_mode').choices]
        order_statuses = [{'id': k, 'name': v} for k, v in OrderStatus.choices if k != OrderStatus.DRAFT]
        
    else:
        orders = []
        filter_cities = transport_modes = order_statuses = []

    context = {
        'orders': orders,
        'filter_cities': filter_cities,
        'transport_modes': transport_modes,
        'order_statuses': order_statuses,
    }
    
    # اطمینان از بازگشت رندر برای درخواست‌های GET
    return render(request, 'forwarder_panel/order_list.html', context)

@login_required
@forwarder_required
@staff_permission_required('can_view_orders')
def order_detail_view(request, order_id):
    """
    نمایش جزئیات سفارش برای فورواردر.

    این ویو فقط سفارش‌هایی را نمایش می‌دهد که نرخ انتخاب‌شده آن‌ها متعلق به
    شرکت فورواردر کاربر فعلی باشد. همچنین برای جلوگیری از N+1 Query، روابط
    پرتکرار با select_related و prefetch_related بارگذاری می‌شوند.

    قابلیت‌ها:
    - نمایش اطلاعات کامل سفارش
    - تغییر وضعیت سفارش توسط فورواردر
    - نمایش مدارک اصلی سفارش
    - نمایش درخواست‌های مدارک تکمیلی
    - نمایش فایل‌های آپلودشده توسط مشتری برای مدارک تکمیلی
    """

    forwarder_company = get_company_for_user(request.user)

    order = get_object_or_404(
        CargoRequest.objects.select_related(
            "customer",
            "selected_rate",
            "selected_rate__forwarder",
            "origin_city",
            "origin_city__province",
            "destination_port",
            "destination_port__city",
            "destination_port__city__country",
            "cargo_type",
        ).prefetch_related(
            "cargo_subcategories",
            "dimensions",
            "cargo_items__subcategory",
            "cargo_items__child",
        ),
        id=order_id,
        selected_rate__forwarder=forwarder_company,
    )

    # -------------------------------------------------------------------------
    # پردازش فرم تغییر وضعیت سفارش
    # -------------------------------------------------------------------------
    if request.method == "POST":
        if not staff_perm(request.user, 'can_update_order_status'):
            messages.error(request, "شما دسترسی تغییر وضعیت سفارش را ندارید.")
            return redirect("forwarder_panel:order_detail", order_id=order_id)

        new_status = request.POST.get("status")
        note = request.POST.get("note", "")

        if new_status and new_status in dict(OrderStatus.choices):
            old_status = order.status

            if old_status != new_status:
                with transaction.atomic():
                    order.status = new_status
                    order.save(update_fields=["status"])

                    OrderHistory.objects.create(
                        order=order,
                        changed_by=request.user,
                        field_name="status",
                        old_value=old_status,
                        new_value=new_status,
                        note=note,
                    )

                    CustomerNotification.objects.create(
                        user=order.customer,
                        notif_type=CustomerNotification.NotifType.ORDER_STATUS,
                        title=f"وضعیت سفارش #{order.id} تغییر کرد",
                        subtitle=f"وضعیت جدید: {dict(OrderStatus.choices).get(new_status, new_status)}",
                        url=f"/auth/profile/orders/{order.id}/",
                        order=order,
                    )

                messages.success(request, "وضعیت سفارش با موفقیت بروزرسانی شد.")
            else:
                messages.info(request, "وضعیت انتخاب‌شده با وضعیت فعلی سفارش یکسان است.")

            return redirect("forwarder_panel:order_detail", order_id=order.id)

        messages.error(request, "وضعیت انتخاب‌شده معتبر نیست.")
        return redirect("forwarder_panel:order_detail", order_id=order.id)

    # -------------------------------------------------------------------------
    # مدارک اصلی سفارش
    # -------------------------------------------------------------------------
    order_documents = (
        OrderDocument.objects
        .filter(order=order)
        .select_related("order", "uploaded_by", "reviewed_by")
        .order_by("-created_at")
    )

    # -------------------------------------------------------------------------
    # درخواست‌های مدرک تکمیلی و فایل‌های آپلودشده توسط مشتری
    # related_name در مدل آپلود باید uploads باشد.
    # -------------------------------------------------------------------------
    additional_document_requests = (
        AdditionalDocumentRequest.objects
        .filter(order=order)
        .select_related("order", "requested_by")
        .prefetch_related("uploads")
        .order_by("-created_at")
    )

    order_messages = (
        OrderMessage.objects
        .filter(order=order)
        .select_related("sender")
        .order_by("created_at")
    )
    # Mark forwarder as having read all messages
    OrderMessage.objects.filter(order=order, is_read_by_forwarder=False).update(is_read_by_forwarder=True)

    context = {
        "order": order,
        "statuses": OrderStatus.choices,
        "order_documents": order_documents,
        "additional_document_requests": additional_document_requests,
        "order_messages": order_messages,
    }

    return render(request, "forwarder_panel/order_detail.html", context)

@login_required
@forwarder_required
def dashboard_view(request):
    forwarder_company = get_company_for_user(request.user)
    
    # تاریخ ۷ روز پیش
    seven_days_ago = timezone.now() - timedelta(days=7)
    
    # فیلتر سفارشات مرتبط با این فورواردر در ۷ روز گذشته (بدون در نظر گرفتن پیش‌نویس‌ها)
    recent_orders = CargoRequest.objects.filter(
        selected_rate__forwarder=forwarder_company,
        created_at__gte=seven_days_ago
    ).exclude(status=OrderStatus.DRAFT)
    
    # 1. تعداد کل سفارشات و مبلغ فروش در 7 روز گذشته
    total_orders_count = recent_orders.count()
    total_sales = recent_orders.aggregate(total=Sum('final_price'))['total'] or 0
    avg_order_amount = recent_orders.aggregate(avg=Avg('final_price'))['avg'] or 0

    # 2. تعداد سفارشات در انتظار تایید (کل، نه فقط هفته اخیر)
    pending_payment_count = CargoRequest.objects.filter(
        selected_rate__forwarder=forwarder_company,
        status=OrderStatus.PENDING,
    ).count()

    # 3. تعداد مقصدهای فعال (unique destination ports در سفارشات غیر draft)
    active_destinations_count = CargoRequest.objects.filter(
        selected_rate__forwarder=forwarder_company,
    ).exclude(status=OrderStatus.DRAFT).values('destination_port').distinct().count()

    # 4. پرفروش‌ترین روش حمل در 7 روز گذشته
    top_transport_mode = recent_orders.values('transport_mode').annotate(
        order_count=Count('id'),
        total_sales=Sum('final_price')
    ).order_by('-order_count').first()

    mode_choices = dict(TransportMode.choices)
    if top_transport_mode:
        top_transport_mode['display_name'] = mode_choices.get(top_transport_mode['transport_mode'], top_transport_mode['transport_mode'])

    # 5. پرتردد‌ترین مقصد در 7 روز گذشته
    top_destination = recent_orders.values('destination_port__city__name').annotate(
        order_count=Count('id'),
        total_sales=Sum('final_price')
    ).order_by('-order_count').first()

    # 6. آمار نرخ‌های فعال این فورواردر
    active_rates = Rate.objects.filter(forwarder=forwarder_company, is_active=True)
    total_active_rates = active_rates.count()

    rates_by_route = active_rates.values(
        'origin_city__name',
        'destination_city__name',
        'transport_mode'
    ).annotate(rate_count=Count('id')).order_by('-rate_count')
    for r in rates_by_route:
        r['mode_display'] = mode_choices.get(r['transport_mode'], r['transport_mode'])

    context = {
        'total_orders_count': total_orders_count,
        'total_sales': total_sales,
        'avg_order_amount': int(avg_order_amount),
        'pending_payment_count': pending_payment_count,
        'active_destinations_count': active_destinations_count,
        'top_transport_mode': top_transport_mode,
        'top_destination': top_destination,
        'total_active_rates': total_active_rates,
        'rates_by_route': rates_by_route,
    }
    
    return render(request, 'forwarder_panel/dashboard.html', context)
@login_required
@forwarder_required
@staff_permission_required('can_view_reports')
def get_sales_chart_data(request):
    """
    دریافت داده‌های نمودار فروش بر اساس بازه زمانی و تاریخ (فرمت تاریخ شمسی است).
    """
    forwarder_company = get_company_for_user(request.user)
    
    # دریافت پارامترها از درخواست GET
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    interval = request.GET.get('interval', 'daily')

    # فیلتر پایه: سفارشات متعلق به این شرکت که پیش‌نویس نیستند
    orders = CargoRequest.objects.filter(
        selected_rate__forwarder=forwarder_company
    ).exclude(status=OrderStatus.DRAFT)

    # تبدیل تاریخ شمسی به میلادی و اعمال فیلتر تاریخ
    try:
        if start_date_str:
            y, m, d = map(int, start_date_str.split('/'))
            start_date = jdatetime.date(y, m, d).togregorian()
            orders = orders.filter(created_at__date__gte=start_date)
        
        if end_date_str:
            y, m, d = map(int, end_date_str.split('/'))
            end_date = jdatetime.date(y, m, d).togregorian()
            orders = orders.filter(created_at__date__lte=end_date)
    except Exception as e:
        return JsonResponse({'error': 'فرمت تاریخ نامعتبر است. لطفاً فرمت YYYY/MM/DD را رعایت کنید.'}, status=400)

    # انتخاب نوع گروه‌بندی (Truncation) بر اساس بازه زمانی
    trunc_mapping = {
        'daily': TruncDay('created_at'),
        'weekly': TruncWeek('created_at'),
        'monthly': TruncMonth('created_at'),
        'quarterly': TruncQuarter('created_at'),
        'yearly': TruncYear('created_at'),
    }
    
    trunc_func = trunc_mapping.get(interval, TruncDay('created_at'))

    # گروه‌بندی داده‌ها و محاسبه مجموع مبالغ (فروش)
    sales_data = orders.annotate(
        period=trunc_func
    ).values('period').annotate(
        total_sales=Sum('final_price')
    ).order_by('period')

    # آماده‌سازی آرایه‌ها برای خروجی JSON (فرانت‌اند)
    dates = []
    amounts = []

    for item in sales_data:
        if item['period']:
            # تبدیل مجدد تاریخ میلادی دیتابیس به رشته شمسی برای نمایش در نمودار
            jalali_date = jdatetime.datetime.fromgregorian(datetime=item['period']).strftime('%Y/%m/%d')
            dates.append(jalali_date)
            # اگر مقداری ثبت نشده بود صفر در نظر بگیرد
            amounts.append(item['total_sales'] or 0)

    return JsonResponse({
        'dates': dates,
        'amounts': amounts
    })
@login_required
@forwarder_required
@staff_permission_required('can_view_reports')
def report_view(request):
    """
    نمایش صفحه اصلی گزارشات شامل نمودار فروش
    """
    return render(request, 'forwarder_panel/report.html')
@login_required
@forwarder_required
@staff_permission_required('can_request_documents')
@require_POST
def request_additional_document(request, order_id):
    """ثبت درخواست مدرک تکمیلی از مشتری توسط فورواردر + ارسال پیامک به مشتری."""

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    forwarder_company = get_company_for_user(request.user)

    order = get_object_or_404(
        CargoRequest.objects.select_related(
            "customer",
            "selected_rate",
            "selected_rate__forwarder",
        ),
        id=order_id,
        selected_rate__forwarder=forwarder_company,
    )

    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()

    if not title:
        if is_ajax:
            return JsonResponse({"success": False, "error": "عنوان مدرک تکمیلی الزامی است."}, status=400)
        messages.error(request, "عنوان مدرک تکمیلی الزامی است.")
        return redirect("forwarder_panel:order_detail", order_id=order.id)

    doc_request = AdditionalDocumentRequest.objects.create(
        order=order,
        requested_by=request.user,
        title=title,
        custom_document_title=title,
        description=description or "",
    )

    CustomerNotification.objects.create(
        user=order.customer,
        notif_type=CustomerNotification.NotifType.DOC_REQUEST,
        title=f"درخواست مدرک جدید: {title}",
        subtitle=f"سفارش #{order.id}",
        url=f"/auth/profile/orders/{order.id}/",
        order=order,
    )

    _send_doc_request_sms(request, order, doc_request)

    if is_ajax:
        return JsonResponse({
            "success": True,
            "request": {
                "id": doc_request.id,
                "title": title,
                "description": description,
                "status": "open",
                "created_at": doc_request.created_at.strftime("%Y/%m/%d"),
            },
        })
    messages.success(request, "درخواست مدرک تکمیلی با موفقیت ثبت و پیامک به مشتری ارسال شد.")
    return redirect("forwarder_panel:order_detail", order_id=order.id)


def _send_doc_request_sms(request, order, doc_request):
    """ارسال پیامک اطلاع‌رسانی درخواست مدرک به مشتری."""
    from django.conf import settings as django_settings
    from core.services.notifications.sms import SmsNotificationService

    template_cfg = django_settings.SMS_TEMPLATES.get("doc_request_link", {})
    template_id = template_cfg.get("template_id", 0)
    if not template_id:
        return  # قالب در sms.ir هنوز تنظیم نشده

    customer_mobile = order.customer.mobile
    if not customer_mobile:
        return

    upload_path = doc_request.get_upload_url()
    full_link = request.build_absolute_uri(upload_path)

    try:
        svc = SmsNotificationService()
        svc.send_template(
            mobile=customer_mobile,
            template_key="doc_request_link",
            context={
                "order_id": str(order.id),
                "doc_title": doc_request.document_title,
                "link": full_link,
            },
        )
        doc_request.sms_sent_at = timezone.now()
        doc_request.save(update_fields=["sms_sent_at"])
    except Exception:
        pass  # عدم ارسال SMS نباید جریان اصلی را مختل کند


@login_required
@forwarder_required
@staff_permission_required('can_manage_documents')
@require_POST
def update_document_status(request, doc_id):
    """تغییر وضعیت مدرک اصلی سفارش توسط فورواردر (AJAX یا فرم معمولی)."""

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    forwarder_company = get_company_for_user(request.user)

    doc = get_object_or_404(
        OrderDocument.objects.select_related(
            "order",
            "order__customer",
            "order__selected_rate",
            "order__selected_rate__forwarder",
            "document_type",
        ),
        id=doc_id,
        order__selected_rate__forwarder=forwarder_company,
    )

    status = request.POST.get("status")
    reason = request.POST.get("reason", "").strip()

    if status == "approved":
        doc.approve(request.user)
        CustomerNotification.objects.create(
            user=doc.order.customer,
            notif_type=CustomerNotification.NotifType.DOC_STATUS,
            title=f"مدرک «{doc.document_type.title}» تأیید شد",
            subtitle=f"سفارش #{doc.order_id}",
            url=f"/auth/profile/orders/{doc.order_id}/",
            order=doc.order,
        )
        if is_ajax:
            return JsonResponse({"success": True, "new_status": "approved", "status_label": "تایید شده"})
        messages.success(request, "مدرک با موفقیت تأیید شد.")

    elif status == "rejected":
        if not reason:
            if is_ajax:
                return JsonResponse({"success": False, "error": "برای رد کردن مدرک، وارد کردن دلیل رد الزامی است."}, status=400)
            messages.error(request, "برای رد کردن مدرک، وارد کردن دلیل رد الزامی است.")
            return redirect("forwarder_panel:order_detail", order_id=doc.order.id)
        doc.reject(request.user, reason)
        CustomerNotification.objects.create(
            user=doc.order.customer,
            notif_type=CustomerNotification.NotifType.DOC_STATUS,
            title=f"مدرک «{doc.document_type.title}» رد شد",
            subtitle=f"سفارش #{doc.order_id} — {reason}",
            url=f"/auth/profile/orders/{doc.order_id}/",
            order=doc.order,
        )
        if is_ajax:
            return JsonResponse({"success": True, "new_status": "rejected", "status_label": "رد شده"})
        messages.success(request, "مدرک با موفقیت رد شد.")

    else:
        if is_ajax:
            return JsonResponse({"success": False, "error": "وضعیت انتخاب‌شده برای مدرک معتبر نیست."}, status=400)
        messages.error(request, "وضعیت انتخاب‌شده برای مدرک معتبر نیست.")

    return redirect("forwarder_panel:order_detail", order_id=doc.order.id)


@login_required
@forwarder_required
@staff_permission_required('can_send_order_message')
@require_POST
def send_order_message(request, order_id):
    """ارسال پیام از طرف فورواردر برای مشتری در یک سفارش (AJAX)."""

    forwarder_company = get_company_for_user(request.user)
    order = get_object_or_404(
        CargoRequest.objects.select_related("customer", "selected_rate", "selected_rate__forwarder"),
        id=order_id,
        selected_rate__forwarder=forwarder_company,
    )

    content = request.POST.get("content", "").strip()
    if not content:
        return JsonResponse({"success": False, "error": "متن پیام نمی‌تواند خالی باشد."}, status=400)

    msg = OrderMessage.objects.create(
        order=order,
        sender=request.user,
        sender_role=OrderMessage.SenderRole.FORWARDER,
        content=content,
        is_read_by_customer=False,
        is_read_by_forwarder=True,
    )

    CustomerNotification.objects.create(
        user=order.customer,
        notif_type=CustomerNotification.NotifType.MESSAGE,
        title=f"پیام جدید از فورواردر",
        subtitle=f"سفارش #{order.id}: {content[:60]}",
        url=f"/auth/profile/orders/{order.id}/",
        order=order,
    )

    return JsonResponse({
        "success": True,
        "message": {
            "id": msg.id,
            "content": msg.content,
            "sender_role": msg.sender_role,
            "created_at": msg.created_at.strftime("%Y/%m/%d - %H:%M"),
        },
    })


@login_required
@forwarder_required
def forwarder_notifications_api(request):
    """بازگشت لیست اعلان‌های خوانده‌نشده فورواردر به صورت JSON."""
    forwarder_company = get_company_for_user(request.user)
    if not forwarder_company:
        return JsonResponse({"count": 0, "items": []})

    qs = ForwarderNotification.objects.filter(
        forwarder_company=forwarder_company,
        is_read=False,
    ).order_by('-created_at')

    items = [
        {
            "id": n.id,
            "title": n.title,
            "subtitle": n.subtitle,
            "url": n.url,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for n in qs
    ]
    return JsonResponse({"count": len(items), "items": items})


@login_required
@forwarder_required
@require_POST
def forwarder_mark_notifications_read(request):
    """علامت‌گذاری همه اعلان‌های فورواردر به عنوان خوانده‌شده."""
    forwarder_company = get_company_for_user(request.user)
    if forwarder_company:
        ForwarderNotification.objects.filter(
            forwarder_company=forwarder_company,
            is_read=False,
        ).update(is_read=True)
    return JsonResponse({"ok": True})


# ==============================================================================
# تنظیمات فورواردر (۱۰-۱ مدیریت نقش‌ها / ۱۰-۲ لوگو / ۱۰-۳ تغییر رمز)
# ==============================================================================

ROLE_PERMISSION_FIELDS = [
    ("can_view_orders",      "مشاهده سفارشات"),
    ("can_manage_orders",    "مدیریت سفارشات"),
    ("can_update_order_status", "تغییر وضعیت سفارش"),
    ("can_send_order_message",  "ارسال پیام در سفارش"),
    ("can_request_documents",   "درخواست مدارک از مشتری"),
    ("can_view_documents",   "مشاهده مدارک"),
    ("can_manage_documents", "تایید/رد مدارک"),
    ("can_view_rates",       "مشاهده نرخ‌ها"),
    ("can_create_rates",     "ایجاد نرخ جدید"),
    ("can_edit_rates",       "ویرایش نرخ‌ها"),
    ("can_delete_rates",     "حذف نرخ‌ها"),
    ("can_bulk_upload_rates","آپلود گروهی نرخ"),
    ("can_view_branches",    "مشاهده شعب"),
    ("can_manage_branches",  "مدیریت شعب"),
    ("can_view_staff",       "مشاهده کارمندان"),
    ("can_manage_staff",     "مدیریت کارمندان"),
    ("can_view_reports",     "مشاهده گزارشات"),
    ("can_export_reports",   "خروجی گزارشات"),
    ("can_view_support",     "مشاهده تیکت‌های پشتیبانی"),
    ("can_reply_support",    "پاسخ و ثبت تیکت"),
    ("can_view_settings",    "مشاهده تنظیمات"),
    ("can_manage_roles",     "مدیریت نقش‌ها و دسترسی‌ها"),
    ("can_upload_logo",      "آپلود لوگو شرکت"),
]

ROLE_PERMISSION_GROUPS = [
    {
        "id": "orders",
        "label": "سفارشات",
        "icon": "fas fa-box",
        "icon_bg": "#fff7ed",
        "icon_color": "#ea580c",
        "perms": [
            ("can_manage_orders",       "مدیریت سفارشات (لیست)"),
            ("can_view_orders",         "مشاهده جزئیات سفارش"),
            ("can_update_order_status", "تغییر وضعیت سفارش"),
            ("can_send_order_message",  "ارسال پیام در سفارش"),
            ("can_request_documents",   "درخواست مدرک از مشتری"),
            ("can_view_documents",      "مشاهده مدارک سفارش"),
            ("can_manage_documents",    "تایید / رد مدارک"),
        ],
    },
    {
        "id": "rates",
        "label": "نرخ‌ها",
        "icon": "fas fa-tags",
        "icon_bg": "#f0fdf4",
        "icon_color": "#16a34a",
        "perms": [
            ("can_view_rates",        "مشاهده نرخ‌ها"),
            ("can_create_rates",      "ایجاد نرخ جدید"),
            ("can_edit_rates",        "ویرایش نرخ‌ها"),
            ("can_delete_rates",      "حذف نرخ‌ها"),
            ("can_bulk_upload_rates", "آپلود گروهی (اکسل)"),
        ],
    },
    {
        "id": "branches",
        "label": "شعب",
        "icon": "fas fa-building",
        "icon_bg": "#eff6ff",
        "icon_color": "#1e40af",
        "perms": [
            ("can_view_branches",   "مشاهده شعب"),
            ("can_manage_branches", "مدیریت شعب (ایجاد / ویرایش)"),
        ],
    },
    {
        "id": "staff",
        "label": "کارمندان",
        "icon": "fas fa-users",
        "icon_bg": "#fdf4ff",
        "icon_color": "#7c3aed",
        "perms": [
            ("can_view_staff",   "مشاهده کارمندان"),
            ("can_manage_staff", "مدیریت کارمندان"),
        ],
    },
    {
        "id": "reports",
        "label": "گزارشات",
        "icon": "fas fa-chart-bar",
        "icon_bg": "#fff7ed",
        "icon_color": "#d97706",
        "perms": [
            ("can_view_reports",   "مشاهده گزارشات"),
            ("can_export_reports", "خروجی گزارشات"),
        ],
    },
    {
        "id": "support",
        "label": "پشتیبانی",
        "icon": "fas fa-headset",
        "icon_bg": "#f0fdfa",
        "icon_color": "#0d9488",
        "perms": [
            ("can_view_support",  "مشاهده تیکت‌های پشتیبانی"),
            ("can_reply_support", "پاسخ و ثبت تیکت"),
        ],
    },
    {
        "id": "settings",
        "label": "تنظیمات",
        "icon": "fas fa-cog",
        "icon_bg": "#f8fafc",
        "icon_color": "#475569",
        "perms": [
            ("can_view_settings", "مشاهده تنظیمات"),
            ("can_manage_roles",  "مدیریت نقش‌ها و دسترسی‌ها"),
            ("can_upload_logo",   "آپلود لوگو شرکت"),
        ],
    },
]


@login_required
@forwarder_required
@staff_permission_required('can_view_settings')
def settings_view(request):
    """صفحه تنظیمات فورواردر — سه تب: نقش‌ها، لوگو، تغییر رمز."""
    forwarder_company = get_company_for_user(request.user)
    roles = ForwarderRole.objects.filter(company=forwarder_company).order_by('name') if forwarder_company else []
    return render(request, 'forwarder_panel/settings.html', {
        'roles': roles,
        'permission_fields': ROLE_PERMISSION_FIELDS,
        'forwarder_company': forwarder_company,
        'active_tab': request.GET.get('tab', 'roles'),
    })


@login_required
@forwarder_required
@staff_permission_required('can_manage_roles')
def role_create_or_edit(request, role_id=None):
    """ایجاد یا ویرایش یک نقش دسترسی فورواردر."""
    forwarder_company = get_company_for_user(request.user)
    if role_id:
        role = get_object_or_404(ForwarderRole, id=role_id, company=forwarder_company)
    else:
        role = None

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'نام نقش الزامی است.')
            return redirect('forwarder_panel:settings')

        if role is None:
            role = ForwarderRole(company=forwarder_company)
        role.name = name
        for field, _ in ROLE_PERMISSION_FIELDS:
            setattr(role, field, request.POST.get(field) == 'on')
        role.save()
        messages.success(request, f'نقش «{role.name}» با موفقیت ذخیره شد.')
        return redirect('forwarder_panel:settings')

    return render(request, 'forwarder_panel/role_form.html', {
        'role': role,
        'permission_fields': ROLE_PERMISSION_FIELDS,
        'perm_groups': ROLE_PERMISSION_GROUPS,
    })


@login_required
@forwarder_required
@staff_permission_required('can_manage_roles')
@require_POST
def role_delete(request, role_id):
    """حذف یک نقش دسترسی."""
    forwarder_company = get_company_for_user(request.user)
    role = get_object_or_404(ForwarderRole, id=role_id, company=forwarder_company)
    role.delete()
    messages.success(request, f'نقش «{role.name}» حذف شد.')
    return redirect('forwarder_panel:settings')


@login_required
@forwarder_required
@staff_permission_required('can_upload_logo')
@require_POST
def upload_company_logo(request):
    """آپلود لوگو شرکت فورواردر."""
    forwarder_company = get_company_for_user(request.user)
    if not forwarder_company:
        return JsonResponse({'success': False, 'error': 'شرکت یافت نشد.'}, status=404)

    logo_file = request.FILES.get('logo')
    if not logo_file:
        return JsonResponse({'success': False, 'error': 'فایل لوگو ارسال نشده.'}, status=400)

    allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/svg+xml']
    if logo_file.content_type not in allowed_types:
        return JsonResponse({'success': False, 'error': 'فرمت فایل مجاز نیست. فقط JPG، PNG، WEBP یا SVG مجاز است.'}, status=400)

    if forwarder_company.logo:
        forwarder_company.logo.delete(save=False)
    forwarder_company.logo = logo_file
    forwarder_company.save(update_fields=['logo'])
    return JsonResponse({'success': True, 'logo_url': forwarder_company.logo.url})


@login_required
@forwarder_required
def change_password_view(request):
    """تغییر رمز عبور فورواردر — دو روش: رمز قدیمی یا OTP."""
    from django.contrib.auth import update_session_auth_hash
    from accounts.models import OTPCode
    from accounts.services import request_otp, verify_otp

    method = request.POST.get('method') if request.method == 'POST' else None

    if request.method == 'POST':
        if method == 'old_password':
            old_pw = request.POST.get('old_password', '')
            new_pw = request.POST.get('new_password', '')
            confirm_pw = request.POST.get('confirm_password', '')

            if not request.user.check_password(old_pw):
                messages.error(request, 'رمز عبور فعلی اشتباه است.')
            elif len(new_pw) < 6:
                messages.error(request, 'رمز عبور جدید باید حداقل ۶ کاراکتر باشد.')
            elif new_pw != confirm_pw:
                messages.error(request, 'رمز عبور جدید و تکرار آن یکسان نیستند.')
            else:
                request.user.set_password(new_pw)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'رمز عبور با موفقیت تغییر یافت.')
            return redirect('forwarder_panel:settings' + '?tab=password')

        elif method == 'send_otp':
            mobile = request.user.mobile
            try:
                request_otp(mobile=mobile, purpose=OTPCode.Purpose.PASSWORD_RESET)
                messages.info(request, f'کد تأیید به شماره {mobile} ارسال شد.')
                return redirect('forwarder_panel:settings' + '?tab=password&otp_sent=1')
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('forwarder_panel:settings' + '?tab=password')

        elif method == 'verify_otp':
            otp_code = request.POST.get('otp_code', '').strip()
            new_pw = request.POST.get('new_password_otp', '')
            confirm_pw = request.POST.get('confirm_password_otp', '')
            mobile = request.user.mobile

            if new_pw != confirm_pw:
                messages.error(request, 'رمز عبور جدید و تکرار آن یکسان نیستند.')
            elif len(new_pw) < 6:
                messages.error(request, 'رمز عبور جدید باید حداقل ۶ کاراکتر باشد.')
            elif not verify_otp(mobile=mobile, purpose=OTPCode.Purpose.PASSWORD_RESET, code=otp_code):
                messages.error(request, 'کد تأیید نامعتبر یا منقضی شده است.')
            else:
                request.user.set_password(new_pw)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, 'رمز عبور با موفقیت از طریق کد OTP تغییر یافت.')
            return redirect('forwarder_panel:settings' + '?tab=password')

    return redirect('forwarder_panel:settings')
