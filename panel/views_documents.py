from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from accounts.models import User, IdentityDocument
from forwarders.models import ForwarderCompany
from forwarders.services import document_checklist, notify_company
from land_freight.models import LandCarrierProfile

from .decorators import forwarder_required, get_company_for_user
from .forms import ForwarderDocumentsForm


def get_forwarder_verification_status(user):
    """
    خروجی:
    - no_company: هنوز اطلاعات شرکت ثبت نشده
    - pending: شرکت ثبت شده ولی تایید نشده
    - rejected: کارشناس یک یا چند مدرک را رد کرده و اصلاح لازم است
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

    if company.is_verified:
        return "inactive", company

    if any(item["status"] == IdentityDocument.Status.REJECTED for item in document_checklist(company)):
        return "rejected", company

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
        # کارمند شرکت: مدارک را فقط ادمین شرکت ارسال می‌کند؛ تا تایید شرکت،
        # به‌جای خطای ۴۰۳ وضعیت شرکت را می‌بیند.
        company = get_company_for_user(user)
        if company is None:
            return HttpResponseForbidden("شما دسترسی مشاهده این صفحه را ندارید.")
        if company.is_operational:
            return redirect("forwarder_panel:dashboard")
        return render(request, "forwarder_panel/company_inactive.html", {"company": company})

    documents = IdentityDocument.objects.filter(user=user).order_by("-created_at")

    if request.method == "POST" and status in ("verified", "inactive"):
        # ارسال دوباره تایید را برمی‌دارد؛ برای شرکت تایید‌شده فقط از مسیر پشتیبانی
        messages.error(request, "اطلاعات شرکت تایید‌شده از این صفحه قابل تغییر نیست؛ با پشتیبانی تماس بگیرید.")
        return redirect("forwarder_panel:documents")

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

                        # دسته‌های خدمات؛ چون ارسال دوباره‌ی مدارک تایید را برمی‌دارد،
                        # هر تغییر دسته دوباره توسط کارشناس بررسی می‌شود.
                        **{
                            field: field in form.cleaned_data["services"]
                            for field, _ in ForwarderDocumentsForm.SERVICE_FIELDS
                        },

                        # مهم:
                        # بعد از ارسال مدارک، شرکت فعال عملیاتی نیست تا کارشناس تایید کند.
                        "is_verified": False,
                        "is_active": False,
                    },
                )

                # هر بارگذاری یک نسخه‌ی تازه است؛ نسخه‌های قبلی برای سابقه‌ی
                # بررسی باقی می‌مانند و آخرین نسخه‌ی هر نوع مدرک معیار تایید است.
                for document_type, uploaded_file in form.uploaded_documents():
                    IdentityDocument.objects.create(
                        user=user,
                        company=company,
                        document_type=document_type,
                        file=uploaded_file,
                        status=IdentityDocument.Status.PENDING,
                    )

                if company.offers_land:
                    profile, _ = LandCarrierProfile.objects.get_or_create(company=company)
                    profile.service_cities.set(form.cleaned_data["land_service_cities"])
                    profile.service_countries.set(form.cleaned_data["land_service_countries"])
                    profile.vehicle_types.set(form.cleaned_data["land_vehicle_types"])

                notify_company(company, "company_registration_received")

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
        "checklist": document_checklist(company) if company else [],
        "verification_status": status,
        "registered_user": user,
    }

    return render(request, "forwarder_panel/documents.html", context)
