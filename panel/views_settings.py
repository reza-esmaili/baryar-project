# ==============================================================================
# تنظیمات فورواردر (۱۰-۱ مدیریت نقش‌ها / ۱۰-۲ لوگو / ۱۰-۳ تغییر رمز)
# ==============================================================================

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.utils import get_client_ip
from forwarders.models import ForwarderRole

from .decorators import forwarder_required, get_company_for_user, staff_permission_required

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

    # SVG عمداً مجاز نیست: می‌تواند حاوی اسکریپت باشد (ریسک XSS ذخیره‌شده).
    # content_type را کلاینت می‌فرستد و قابل جعل است، پس پسوند واقعی فایل هم
    # جداگانه بررسی می‌شود.
    allowed_types = ['image/jpeg', 'image/png', 'image/webp']
    allowed_extensions = ['jpg', 'jpeg', 'png', 'webp']
    ext = logo_file.name.rsplit('.', 1)[-1].lower() if '.' in logo_file.name else ''

    if logo_file.content_type not in allowed_types or ext not in allowed_extensions:
        return JsonResponse({'success': False, 'error': 'فرمت فایل مجاز نیست. فقط JPG، PNG یا WEBP مجاز است.'}, status=400)

    max_size = 2 * 1024 * 1024
    if logo_file.size > max_size:
        return JsonResponse({'success': False, 'error': 'حجم فایل نباید بیشتر از ۲ مگابایت باشد.'}, status=400)

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
                request_otp(mobile=mobile, purpose=OTPCode.Purpose.PASSWORD_RESET, ip_address=get_client_ip(request))
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
