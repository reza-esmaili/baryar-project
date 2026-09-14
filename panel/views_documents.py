from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from accounts.models import User, IdentityDocument
from forwarders.models import ForwarderCompany

from .decorators import forwarder_required
from .forms import ForwarderDocumentsForm


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
