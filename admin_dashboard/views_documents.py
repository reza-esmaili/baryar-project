# admin_dashboard/views_documents.py

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from documents.models import DocumentRule, AdditionalDocumentRequest

from .decorators import platform_staff_required
from .forms import DocumentRuleAdminForm


@login_required
@platform_staff_required
def document_rule_list(request):
    qs = DocumentRule.objects.select_related("document_type").order_by("-priority", "title")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(document_type__title__icontains=q))

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)
    qs_string = params.urlencode()

    context = {"page_obj": page_obj, "q": q, "querystring": qs_string + "&" if qs_string else ""}
    return render(request, "admin_dashboard/document_rule_list.html", context)


@login_required
@platform_staff_required
def document_rule_form(request, pk=None):
    instance = get_object_or_404(DocumentRule, pk=pk) if pk else None

    if request.method == "POST":
        form = DocumentRuleAdminForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "قانون مدرک با موفقیت ذخیره شد.")
            return redirect("staff_dashboard:document_rule_list")
    else:
        form = DocumentRuleAdminForm(instance=instance)

    context = {"form": form, "instance": instance}
    return render(request, "admin_dashboard/document_rule_form.html", context)


@login_required
@platform_staff_required
def additional_document_request_list(request):
    qs = AdditionalDocumentRequest.objects.select_related(
        "order", "document_type", "requested_by"
    ).order_by("-created_at")

    status = request.GET.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)
    qs_string = params.urlencode()

    context = {
        "page_obj": page_obj,
        "statuses": AdditionalDocumentRequest._meta.get_field("status").choices,
        "selected_status": status,
        "querystring": qs_string + "&" if qs_string else "",
    }
    return render(request, "admin_dashboard/additional_document_request_list.html", context)
