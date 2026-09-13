# admin_dashboard/views.py

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import IdentityDocument, User
from forwarders.models import ForwarderCompany, ForwarderBranch, ForwarderStaff
from orders.models import CargoRequest, OrderStatus
from support.models import Ticket, TicketMessage

from .decorators import platform_staff_required
from .forms import ForwarderCompanyForm, ForwarderAdminUserForm, UserForm, BranchForm, StaffForm, OrderForm
from .services import recompute_company_verification


def _querystring(request):
    """کوئری‌استرینگ جاری بدون page، برای نگه‌داشتن فیلترها هنگام صفحه‌بندی."""
    params = request.GET.copy()
    params.pop("page", None)
    qs = params.urlencode()
    return qs + "&" if qs else ""


@login_required
@platform_staff_required
def settings_hub(request):
    return render(request, "admin_dashboard/settings_hub.html", {})


@login_required
@platform_staff_required
def home(request):
    seven_days_ago = timezone.now() - timedelta(days=7)

    context = {
        "total_users": User.objects.count(),
        "orders_this_week": CargoRequest.objects.filter(
            created_at__gte=seven_days_ago
        ).exclude(status=OrderStatus.DRAFT).count(),
        "pending_verifications": ForwarderCompany.objects.filter(is_verified=False).count(),
        "open_tickets": Ticket.objects.exclude(
            status__in=[Ticket.Status.CLOSED]
        ).count(),
    }
    return render(request, "admin_dashboard/home.html", context)


# ─── Users ──────────────────────────────────────────────────────────────────

@login_required
@platform_staff_required
def user_list(request):
    qs = User.objects.all().order_by("-created_at")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(mobile__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )

    role = request.GET.get("role", "").strip()
    if role:
        qs = qs.filter(role=role)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "roles": User.Role.choices,
        "q": q,
        "selected_role": role,
        "querystring": _querystring(request),
    }
    return render(request, "admin_dashboard/user_list.html", context)


@login_required
@platform_staff_required
def user_create(request):
    if request.method == "POST":
        form = UserForm(request.POST)
        if form.is_valid():
            new_user = form.save(commit=False)
            # رمز موقت = شماره موبایل خودش، با اجبار به تغییر در اولین ورود —
            # همان الگوی ساخت کاربر توسط ادمین در بقیه‌ی داشبورد (شرکت فورواردر جدید و...).
            new_user.must_change_password = True
            new_user.set_password(new_user.mobile)
            new_user.save()
            messages.success(
                request,
                f"کاربر با موفقیت ایجاد شد. رمز عبور موقت، شماره موبایل خودش است ({new_user.mobile}) "
                f"و در اولین ورود باید تغییر داده شود.",
            )
            return redirect("staff_dashboard:user_detail", user_id=new_user.id)
    else:
        form = UserForm(initial={"is_active": True})

    return render(request, "admin_dashboard/user_form.html", {"form": form, "instance": None})


@login_required
@platform_staff_required
def user_edit(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        form = UserForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "اطلاعات کاربر با موفقیت بروزرسانی شد.")
            return redirect("staff_dashboard:user_detail", user_id=user_obj.id)
    else:
        form = UserForm(instance=user_obj)

    return render(request, "admin_dashboard/user_form.html", {"form": form, "instance": user_obj})


@login_required
@platform_staff_required
def user_detail(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)

    if request.method == "POST" and request.POST.get("action") == "toggle_active":
        user_obj.is_active = not user_obj.is_active
        user_obj.save(update_fields=["is_active"])
        messages.success(request, "وضعیت فعال‌بودن کاربر بروزرسانی شد.")
        return redirect("staff_dashboard:user_detail", user_id=user_obj.id)

    context = {
        "user_obj": user_obj,
        "customer_profile": getattr(user_obj, "customer_profile", None),
        "customer_company_profile": getattr(user_obj, "customer_company_profile", None),
        "forwarder_company": getattr(user_obj, "forwarder_company", None),
        "forwarder_staff": getattr(user_obj, "forwarder_staff", None),
        "identity_documents": user_obj.documents.all().order_by("-created_at"),
        "recent_orders": CargoRequest.objects.filter(customer=user_obj).order_by("-created_at")[:10],
    }
    return render(request, "admin_dashboard/user_detail.html", context)


# ─── Forwarder companies ────────────────────────────────────────────────────

@login_required
@platform_staff_required
def forwarder_list(request):
    qs = ForwarderCompany.objects.select_related("admin_user").order_by("-created_at")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(company_name__icontains=q) | Q(national_id__icontains=q) | Q(registration_number__icontains=q)
        )

    verified = request.GET.get("verified", "").strip()
    if verified == "1":
        qs = qs.filter(is_verified=True)
    elif verified == "0":
        qs = qs.filter(is_verified=False)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "q": q,
        "verified": verified,
        "querystring": _querystring(request),
    }
    return render(request, "admin_dashboard/forwarder_list.html", context)


@login_required
@platform_staff_required
def forwarder_create(request):
    # پیشوند "admin" لازم است چون هر دو فرم فیلد email دارند؛ بدون پیشوند
    # هر دو روی input#id_email رندر می‌شدند (شناسه تکراری نامعتبر در HTML).
    if request.method == "POST":
        company_form = ForwarderCompanyForm(request.POST, request.FILES)
        user_form = ForwarderAdminUserForm(request.POST, prefix="admin")
        if company_form.is_valid() and user_form.is_valid():
            with transaction.atomic():
                admin_user = user_form.save(commit=False)
                admin_user.role = User.Role.FORWARDER_ADMIN
                admin_user.must_change_password = True
                # رمز موقت = شماره موبایل (همان الگوی BranchForm/StaffForm در
                # panel/forms.py)؛ کاربر با اولین ورود مجبور به تغییر آن می‌شود.
                admin_user.set_password(admin_user.mobile)
                admin_user.save()

                company = company_form.save(commit=False)
                company.admin_user = admin_user
                company.save()

            messages.success(
                request,
                f"شرکت با موفقیت ایجاد شد. رمز عبور موقت کاربر ادمین شرکت، شماره موبایل خودش است "
                f"({admin_user.mobile}) و در اولین ورود باید تغییر داده شود.",
            )
            return redirect("staff_dashboard:forwarder_detail", company_id=company.id)
    else:
        company_form = ForwarderCompanyForm(initial={"is_active": True})
        user_form = ForwarderAdminUserForm(prefix="admin")

    context = {"company_form": company_form, "user_form": user_form, "instance": None}
    return render(request, "admin_dashboard/forwarder_form.html", context)


@login_required
@platform_staff_required
def forwarder_edit(request, company_id):
    company = get_object_or_404(ForwarderCompany, id=company_id)

    if request.method == "POST":
        company_form = ForwarderCompanyForm(request.POST, request.FILES, instance=company)
        if company_form.is_valid():
            company_form.save()
            messages.success(request, "اطلاعات شرکت با موفقیت بروزرسانی شد.")
            return redirect("staff_dashboard:forwarder_edit", company_id=company.id)
    else:
        company_form = ForwarderCompanyForm(instance=company)

    context = {
        "company_form": company_form,
        "user_form": None,
        "instance": company,
        "branches": company.branches.all(),
        "staff": company.staff.select_related("user", "role").all(),
    }
    return render(request, "admin_dashboard/forwarder_form.html", context)


@login_required
@platform_staff_required
def forwarder_branch_form(request, company_id, branch_id=None):
    """
    افزودن/ویرایش شعبه برای یک شرکت فورواردر (معادل BranchInline در
    ForwarderCompanyAdmin در پنل ادمین جنگو). از همان BranchForm پنل فورواردر
    استفاده می‌شود چون منطق ساخت خودکار کاربر (branch_user) را دارد.
    """
    company = get_object_or_404(ForwarderCompany, id=company_id)
    branch = get_object_or_404(ForwarderBranch, id=branch_id, company=company) if branch_id else None

    if request.method == "POST":
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            form.save(forwarder_company=company)
            messages.success(request, "شعبه با موفقیت ذخیره شد.")
            return redirect("staff_dashboard:forwarder_edit", company_id=company.id)
    else:
        form = BranchForm(instance=branch)

    context = {"form": form, "company": company, "branch": branch}
    return render(request, "admin_dashboard/forwarder_branch_form.html", context)


@login_required
@platform_staff_required
def forwarder_branch_toggle_active(request, company_id, branch_id):
    company = get_object_or_404(ForwarderCompany, id=company_id)
    branch = get_object_or_404(ForwarderBranch, id=branch_id, company=company)
    if request.method == "POST":
        branch.is_active = not branch.is_active
        branch.save(update_fields=["is_active"])
        messages.success(request, "وضعیت شعبه بروزرسانی شد.")
    return redirect("staff_dashboard:forwarder_edit", company_id=company.id)


@login_required
@platform_staff_required
def forwarder_staff_form(request, company_id, staff_id=None):
    """افزودن/ویرایش کارمند شرکت فورواردر (معادل StaffInline در پنل ادمین جنگو)."""
    company = get_object_or_404(ForwarderCompany, id=company_id)
    staff_obj = get_object_or_404(ForwarderStaff, id=staff_id, company=company) if staff_id else None

    if request.method == "POST":
        form = StaffForm(request.POST, forwarder_company=company, instance=staff_obj)
        if form.is_valid():
            form.save(forwarder_company=company)
            messages.success(request, "کارمند با موفقیت ذخیره شد.")
            return redirect("staff_dashboard:forwarder_edit", company_id=company.id)
    else:
        form = StaffForm(forwarder_company=company, instance=staff_obj)

    context = {"form": form, "company": company, "staff_obj": staff_obj, "is_edit": staff_obj is not None}
    return render(request, "admin_dashboard/forwarder_staff_form.html", context)


@login_required
@platform_staff_required
def forwarder_staff_toggle_active(request, company_id, staff_id):
    company = get_object_or_404(ForwarderCompany, id=company_id)
    staff_obj = get_object_or_404(ForwarderStaff, id=staff_id, company=company)
    if request.method == "POST":
        new_state = not staff_obj.is_active
        staff_obj.is_active = new_state
        staff_obj.save(update_fields=["is_active"])
        staff_obj.user.is_active = new_state
        staff_obj.user.save(update_fields=["is_active"])
        messages.success(request, "وضعیت حساب کارمند بروزرسانی شد.")
    return redirect("staff_dashboard:forwarder_edit", company_id=company.id)


@login_required
@platform_staff_required
def forwarder_detail(request, company_id):
    company = get_object_or_404(
        ForwarderCompany.objects.select_related("admin_user"),
        id=company_id,
    )

    if request.method == "POST" and request.POST.get("action") == "toggle_active":
        company.is_active = not company.is_active
        company.save(update_fields=["is_active"])
        messages.success(request, "وضعیت فعال‌بودن شرکت بروزرسانی شد.")
        return redirect("staff_dashboard:forwarder_detail", company_id=company.id)

    context = {
        "company": company,
        "identity_documents": company.identity_documents.all().order_by("-created_at"),
        "branches": company.branches.all(),
        "staff": company.staff.select_related("user", "role").all(),
        "doc_statuses": IdentityDocument.Status.choices,
    }
    return render(request, "admin_dashboard/forwarder_detail.html", context)


@login_required
@platform_staff_required
def review_identity_document(request, company_id, doc_id):
    company = get_object_or_404(ForwarderCompany, id=company_id)
    doc = get_object_or_404(IdentityDocument, id=doc_id, company=company)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in dict(IdentityDocument.Status.choices):
            doc.status = new_status
            doc.admin_note = request.POST.get("admin_note", "").strip()
            doc.save(update_fields=["status", "admin_note"])
            recompute_company_verification(company)
            messages.success(request, "وضعیت مدرک بروزرسانی شد.")
        else:
            messages.error(request, "وضعیت انتخاب‌شده معتبر نیست.")

    return redirect("staff_dashboard:forwarder_detail", company_id=company.id)


# ─── Orders ─────────────────────────────────────────────────────────────────

@login_required
@platform_staff_required
def order_list(request):
    qs = CargoRequest.objects.select_related(
        "customer", "selected_rate__forwarder", "origin_city", "destination_port__city__country"
    ).order_by("-created_at")

    q = request.GET.get("q", "").strip()
    if q:
        filters = Q(customer__mobile__icontains=q) | Q(customer__first_name__icontains=q) | Q(customer__last_name__icontains=q)
        if q.isdigit():
            filters |= Q(id=int(q))
        qs = qs.filter(filters)

    status = request.GET.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "statuses": OrderStatus.choices,
        "q": q,
        "selected_status": status,
        "querystring": _querystring(request),
    }
    return render(request, "admin_dashboard/order_list.html", context)


@login_required
@platform_staff_required
def order_detail(request, order_id):
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
            "dimensions",
            "cargo_items__subcategory",
            "cargo_items__child",
        ),
        id=order_id,
    )

    order_documents = order.required_documents.select_related(
        "document_type", "uploaded_by", "reviewed_by"
    ).order_by("-created_at")

    history = order.history.select_related("changed_by").order_by("-created_at")
    order_messages = order.messages.select_related("sender").order_by("created_at")

    context = {
        "order": order,
        "order_documents": order_documents,
        "history": history,
        "order_messages": order_messages,
    }
    return render(request, "admin_dashboard/order_detail.html", context)


@login_required
@platform_staff_required
def order_edit(request, order_id):
    order = get_object_or_404(CargoRequest, id=order_id)
    if request.method == "POST":
        form = OrderForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, "اطلاعات سفارش با موفقیت بروزرسانی شد.")
            return redirect("staff_dashboard:order_detail", order_id=order.id)
    else:
        form = OrderForm(instance=order)
    context = {"form": form, "order": order}
    return render(request, "admin_dashboard/order_form.html", context)


# ─── Support tickets ────────────────────────────────────────────────────────

@login_required
@platform_staff_required
def ticket_list(request):
    qs = Ticket.objects.select_related("user", "department", "topic").order_by("-created_at")

    status = request.GET.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(subject__icontains=q) | Q(user__mobile__icontains=q))

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "statuses": Ticket.Status.choices,
        "q": q,
        "selected_status": status,
        "querystring": _querystring(request),
    }
    return render(request, "admin_dashboard/ticket_list.html", context)


@login_required
@platform_staff_required
def ticket_detail(request, ticket_id):
    ticket = get_object_or_404(
        Ticket.objects.select_related("user", "department", "topic"),
        id=ticket_id,
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "reply":
            message_text = request.POST.get("message", "").strip()
            if message_text:
                # همان منطق TicketAdmin.save_formset در support/admin.py:
                # پیام جدید با sender=کاربر جاری ثبت می‌شود و اگر تیکت بسته
                # نباشد، وضعیتش به «پاسخ داده شد» تغییر می‌کند.
                TicketMessage.objects.create(
                    ticket=ticket,
                    sender=request.user,
                    message=message_text,
                    attachment=request.FILES.get("attachment"),
                )
                if ticket.status != Ticket.Status.CLOSED:
                    ticket.status = Ticket.Status.ANSWERED
                    ticket.save(update_fields=["status"])
                messages.success(request, "پاسخ ثبت شد.")
            else:
                messages.error(request, "متن پیام نمی‌تواند خالی باشد.")

        elif action == "set_status":
            new_status = request.POST.get("status")
            if new_status in dict(Ticket.Status.choices):
                ticket.status = new_status
                ticket.save(update_fields=["status"])
                messages.success(request, "وضعیت تیکت بروزرسانی شد.")

        return redirect("staff_dashboard:ticket_detail", ticket_id=ticket.id)

    context = {
        "ticket": ticket,
        "ticket_messages": ticket.messages.select_related("sender").order_by("created_at"),
        "activities": ticket.activities.select_related("user").order_by("-created_at"),
        "statuses": Ticket.Status.choices,
    }
    return render(request, "admin_dashboard/ticket_detail.html", context)
