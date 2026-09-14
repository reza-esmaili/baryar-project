# ==============================================================================
# مدیریت سفارشات فورواردر
# ==============================================================================

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from documents.models import AdditionalDocumentRequest, OrderDocument
from locations.models import City
from orders.models import (
    CargoRequest,
    CustomerNotification,
    ForwarderNotification,
    OrderHistory,
    OrderMessage,
    OrderStatus,
)

from .decorators import forwarder_required, get_company_for_user, staff_perm, staff_permission_required


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

    paginator = Paginator(orders, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    context = {
        'orders': page_obj,
        'page_obj': page_obj,
        'querystring': querystring + '&' if querystring else '',
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
    """ارسال ناهمزمان پیامک اطلاع‌رسانی درخواست مدرک به مشتری."""
    from panel.tasks import send_doc_request_sms_task

    customer_mobile = order.customer.mobile
    if not customer_mobile:
        return

    upload_path = doc_request.get_upload_url()
    full_link = request.build_absolute_uri(upload_path)

    send_doc_request_sms_task.delay(
        doc_request.id, order.id, customer_mobile, doc_request.document_title, full_link,
    )


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
