from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.utils import get_client_ip
from forwarders.models import ForwarderStaff

from .decorators import forwarder_required, get_company_for_user, staff_permission_required
from .forms import StaffForm


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
                request_otp(user.mobile, OTPCode.Purpose.PASSWORD_RESET, ip_address=get_client_ip(request))
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
