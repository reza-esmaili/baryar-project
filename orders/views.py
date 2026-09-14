from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from decimal import Decimal
from weasyprint import HTML

from .forms import CargoRequestForm, CargoDimensionFormSet, OrderCompletionForm
from .services import calculate_and_match_rates, calculate_extra_charge, money, get_forwarder_notification_target
from .models import CargoRequest, OrderStatus, OrderHistory, OrderCargoItem
from rates.models import CargoType, Rate, CargoSubCategory, CargoSubCategoryChild, ExtraChargeType
from documents.services import sync_order_required_documents, OrderDocument
from orders.crosssite import consume_order_token
from core.services.notifications.tasks import notify_task
from core.services.notifications.events import (
    ORDER_DRAFT_CREATED,
    RATE_MATCH_FOUND_CUSTOMER,
    RATE_MATCH_FOUND_FORWARDER,
    ORDER_FINALIZED,
)


# ════════════════════════════════════════════════════════════════
# Helper ها
# ════════════════════════════════════════════════════════════════

def _get_user_profile_data(user):
    """استخراج کد ملی و آدرس از پروفایل کاربر برای تمپلیت."""
    national_id = ""
    address = ""
    if hasattr(user, "customer_profile") and user.customer_profile:
        national_id = user.customer_profile.national_code or ""
        address = user.customer_profile.address or ""
    elif hasattr(user, "customer_company_profile") and user.customer_company_profile:
        national_id = user.customer_company_profile.national_id or ""
        address = user.customer_company_profile.address or ""
    return national_id, address


def _sync_user_profile_from_order(request, form, order):
    """
    اگر تیک «برای فرد دیگری» نخورده باشد،
    اطلاعات فرستنده در پروفایل کاربر هم ذخیره می‌شود.
    """
    is_for_other = form.cleaned_data.get('is_for_other', False)
    if is_for_other:
        return

    user = request.user

    first_name = (form.cleaned_data.get('sender_first_name') or '').strip()
    last_name = (form.cleaned_data.get('sender_last_name') or '').strip()
    national_id = (form.cleaned_data.get('sender_national_id') or '').strip()
    address = form.cleaned_data.get('sender_address') or ''

    # به‌روزرسانی User
    user_changed = False
    if first_name and user.first_name != first_name:
        user.first_name = first_name
        user_changed = True
    if last_name and user.last_name != last_name:
        user.last_name = last_name
        user_changed = True
    if user_changed:
        user.save(update_fields=['first_name', 'last_name'])

    # به‌روزرسانی CustomerProfile
    from accounts.models import CustomerProfile
    profile, _ = CustomerProfile.objects.get_or_create(
        user=user,
        defaults={'national_code': national_id or ''}
    )
    profile_changed = False

    if national_id and profile.national_code != national_id:
        conflict = CustomerProfile.objects.filter(
            national_code=national_id
        ).exclude(user=user).exists()
        if not conflict:
            profile.national_code = national_id
            profile_changed = True

    if address and profile.address != address:
        profile.address = address
        profile_changed = True

    if profile_changed:
        profile.save()


def _save_cargo_items(request, order):
    """
    خواندن ردیف‌های جزئیات کالا از POST و ذخیره در OrderCargoItem.
    item_subcategory[] / item_child[] / item_other_text[]
    """
    OrderCargoItem.objects.filter(order=order).delete()

    subcats = request.POST.getlist('item_subcategory[]')
    children = request.POST.getlist('item_child[]')
    other_texts = request.POST.getlist('item_other_text[]')

    for idx, sub_id in enumerate(subcats):
        if not sub_id:
            continue

        try:
            subcategory = CargoSubCategory.objects.get(id=sub_id)
        except CargoSubCategory.DoesNotExist:
            continue

        child_val = children[idx] if idx < len(children) else ''
        other_text = other_texts[idx] if idx < len(other_texts) else ''

        if child_val == 'other':
            OrderCargoItem.objects.create(
                order=order,
                subcategory=subcategory,
                child=None,
                is_other=True,
                other_child_name=other_text.strip() or 'سایر',
            )
        elif child_val:
            try:
                child = CargoSubCategoryChild.objects.get(
                    id=child_val, subcategory=subcategory
                )
                OrderCargoItem.objects.create(
                    order=order,
                    subcategory=subcategory,
                    child=child,
                    is_other=False,
                )
            except CargoSubCategoryChild.DoesNotExist:
                continue
        else:
            OrderCargoItem.objects.create(
                order=order,
                subcategory=subcategory,
                child=None,
                is_other=False,
            )


# ════════════════════════════════════════════════════════════════
# مرحله اول ثبت سفارش
# ════════════════════════════════════════════════════════════════

@login_required
def create_cargo_request(request):
    form = CargoRequestForm()
    formset = CargoDimensionFormSet()
    return render(request, 'customer_panel/create_request.html', {
        'form': form,
        'formset': formset
    })


@login_required
def ajax_calculate_rates(request):
    if request.method == 'POST':
        form = CargoRequestForm(request.POST)
        formset = CargoDimensionFormSet(request.POST)

        if form.is_valid():
            is_fcl = form.cleaned_data.get('transport_mode') in ['sea_fcl', 'FCL']

            if is_fcl or formset.is_valid():
                dimensions_data = [] if is_fcl else formset.cleaned_data
                match_data = calculate_and_match_rates(form.cleaned_data, dimensions_data)

                return JsonResponse({
                    'success': True,
                    'actual_weight': match_data.get('actual_weight', 0),
                    'volumetric_weight': match_data.get('volumetric_weight', 0),
                    'chargeable_weight': match_data.get('chargeable_weight', 0),
                    'rates': match_data['results']
                })

        return JsonResponse({'success': False, 'errors': form.errors})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
def submit_order(request):
    if request.method == 'POST':
        form = CargoRequestForm(request.POST)
        formset = CargoDimensionFormSet(request.POST)
        selected_rate_id = request.POST.get('selected_rate_id')

        if form.is_valid() and selected_rate_id:
            is_fcl = form.cleaned_data.get('transport_mode') in ['sea_fcl', 'FCL']

            if is_fcl or formset.is_valid():
                dimensions_data = [] if is_fcl else formset.cleaned_data
                match_data = calculate_and_match_rates(form.cleaned_data, dimensions_data)

                selected_result = None
                for item in match_data["results"]:
                    if str(item["rate_id"]) == str(selected_rate_id):
                        selected_result = item
                        break

                if not selected_result:
                    messages.error(request, "نرخ انتخاب شده معتبر نیست یا منقضی شده است.")
                    return redirect('orders:create_request')

                cargo_request = form.save(commit=False)
                cargo_request.customer = request.user

                rate = get_object_or_404(Rate, id=selected_rate_id)

                if rate.transport_mode != cargo_request.transport_mode:
                    messages.error(request, "نرخ انتخاب‌شده با روش حمل سفارش مطابقت ندارد.")
                    return redirect('orders:create_request')

                if rate.shipping_procedure != cargo_request.shipping_procedure:
                    messages.error(request, "نرخ انتخاب‌شده با رویه ارسال سفارش مطابقت ندارد.")
                    return redirect('orders:create_request')

                cargo_request.selected_rate = rate
                cargo_request.needs_office_packaging = form.cleaned_data.get('needs_office_packaging', False)
                cargo_request.needs_onsite_packaging = form.cleaned_data.get('needs_onsite_packaging', False)
                cargo_request.needs_doorstep_packaging = form.cleaned_data.get('needs_doorstep_packaging', False)
                cargo_request.chargeable_weight = match_data["chargeable_weight"]
                cargo_request.base_shipping_price = selected_result.get("base_shipping_price", 0)
                cargo_request.office_packaging_price = selected_result.get("office_packaging_price", 0)
                cargo_request.onsite_packaging_price = selected_result.get("onsite_packaging_price", 0)
                cargo_request.doorstep_packaging_price = selected_result.get("doorstep_packaging_price", 0)
                cargo_request.vat_amount = selected_result.get("vat_amount", 0)
                cargo_request.price_subtotal = selected_result.get("subtotal", 0)
                cargo_request.final_price = selected_result.get("total_price", 0)
                cargo_request.status = OrderStatus.DRAFT

                if is_fcl:
                    cargo_request.container_size = form.cleaned_data.get('container_size')
                    cargo_request.container_type = form.cleaned_data.get('container_type')
                    cargo_request.container_count = form.cleaned_data.get('container_count')

                cargo_request.save()

                if not is_fcl:
                    dimensions = formset.save(commit=False)
                    for dim in dimensions:
                        dim.cargo_request = cargo_request
                        dim.save()

                OrderHistory.objects.create(
                    order=cargo_request,
                    changed_by=request.user,
                    note="نرخ انتخاب شد و سفارش به عنوان پیش‌نویس ثبت گردید."
                )

                customer_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.mobile
                origin_name = cargo_request.origin_city.name if cargo_request.origin_city_id else ""
                destination_name = cargo_request.destination_port.name if cargo_request.destination_port_id else ""

                notify_task.delay(ORDER_DRAFT_CREATED, request.user.mobile, {
                    "order_id": cargo_request.id,
                    "customer_name": customer_name,
                    "origin": origin_name,
                    "destination": destination_name,
                })

                forwarder_name = (rate.forwarder.company_name if rate.forwarder_id
                                  else rate.branch.company.company_name if rate.branch_id else "")
                notify_task.delay(RATE_MATCH_FOUND_CUSTOMER, request.user.mobile, {
                    "order_id": cargo_request.id,
                    "forwarder_name": forwarder_name,
                })

                forwarder_mobile, _ = get_forwarder_notification_target(rate)
                notify_task.delay(RATE_MATCH_FOUND_FORWARDER, forwarder_mobile, {
                    "order_id": cargo_request.id,
                    "origin": origin_name,
                    "destination": destination_name,
                    "customer_name": customer_name,
                })

                return redirect('orders:complete_order_details', order_id=cargo_request.id)

    return redirect('orders:create_request')


# ════════════════════════════════════════════════════════════════
# مرحله دوم — تکمیل سفارش
# ════════════════════════════════════════════════════════════════

@login_required
def complete_order_details(request, order_id):
    cargo_request = get_object_or_404(
        CargoRequest, id=order_id, customer=request.user,
    )
    selected_rate = cargo_request.selected_rate

    doorstep_option = None
    if selected_rate and selected_rate.doorstep_packaging_charge_type != ExtraChargeType.NOT_AVAILABLE:
        doorstep_amount = calculate_extra_charge(
            selected_rate.doorstep_packaging_charge_type,
            selected_rate.doorstep_packaging_price,
            cargo_request.chargeable_weight
        )

        doorstep_hint = ""
        if selected_rate.doorstep_packaging_charge_type == ExtraChargeType.FREE:
            doorstep_label = "رایگان"
        elif selected_rate.doorstep_packaging_charge_type == ExtraChargeType.FIXED:
            doorstep_label = f"{money(doorstep_amount):,} ریال"
            doorstep_hint = "هزینه ثابت"
        elif selected_rate.doorstep_packaging_charge_type == ExtraChargeType.PER_KG:
            doorstep_label = f"{money(doorstep_amount):,} ریال"
            doorstep_hint = f"بر اساس وزن محاسبه‌شده: {cargo_request.chargeable_weight} کیلوگرم"
        else:
            doorstep_label = ""

        doorstep_option = {
            "amount": doorstep_amount,
            "label": doorstep_label,
            "hint": doorstep_hint if selected_rate.doorstep_packaging_charge_type != ExtraChargeType.FREE else "",
            "charge_type": selected_rate.doorstep_packaging_charge_type,
        }

    sync_order_required_documents(cargo_request)

    if request.method == "POST":
        form = OrderCompletionForm(
            request.POST, request.FILES,
            instance=cargo_request, user=request.user
        )

        if form.is_valid():
            order = form.save(commit=False)

            order.sender_city = order.origin_city
            order.sender_province = order.origin_city.province

            wants_doorstep = request.POST.get("needs_doorstep_packaging") == "on"
            order.needs_doorstep_packaging = False
            order.doorstep_packaging_price = 0

            if wants_doorstep and order.selected_rate:
                rate = order.selected_rate
                if rate.doorstep_packaging_charge_type != ExtraChargeType.NOT_AVAILABLE:
                    doorstep_amount = calculate_extra_charge(
                        rate.doorstep_packaging_charge_type,
                        rate.doorstep_packaging_price,
                        order.chargeable_weight
                    )
                    order.needs_doorstep_packaging = True
                    order.doorstep_packaging_price = money(doorstep_amount)

                    base_shipping_price = Decimal(str(order.base_shipping_price or 0))
                    office_packaging_price = Decimal(str(order.office_packaging_price or 0))
                    onsite_packaging_price = Decimal(str(order.onsite_packaging_price or 0))
                    doorstep_price = Decimal(str(order.doorstep_packaging_price or 0))

                    subtotal = (
                        base_shipping_price + office_packaging_price
                        + onsite_packaging_price + doorstep_price
                    )

                    if rate.add_vat:
                        vat_amount = subtotal * Decimal("0.10")
                    else:
                        vat_amount = Decimal("0.00")

                    order.price_subtotal = money(subtotal)
                    order.vat_amount = money(vat_amount)
                    order.final_price = money(subtotal + vat_amount)

            order.status = OrderStatus.PENDING

            # همگام‌سازی پروفایل کاربر
            _sync_user_profile_from_order(request, form, order)

            order.save()
            form.save_m2m()

            # ذخیره اقلام کالا
            _save_cargo_items(request, order)

            # sync دوباره مدارک
            sync_order_required_documents(order)

            documents = OrderDocument.objects.select_related(
                "document_type"
            ).filter(order=order)

            for doc in documents:
                uploaded_file = request.FILES.get(f"doc_{doc.id}")
                if uploaded_file:
                    doc.file = uploaded_file
                    doc.uploaded_by = request.user
                    doc.status = "uploaded"
                    doc.save()

            OrderHistory.objects.create(
                order=order,
                changed_by=request.user,
                note="اطلاعات سفارش تکمیل و مدارک بارگذاری شد و سفارش ثبت نهایی گردید."
            )

            notify_task.delay(ORDER_FINALIZED, request.user.mobile, {
                "order_id": order.id,
                "final_price": order.final_price,
            })

            return redirect("customer:order_detail", pk=order.id)

        # ── فرم نامعتبر — رندر مجدد با خطاها ──
        documents = OrderDocument.objects.select_related(
            "document_type"
        ).filter(order=cargo_request).order_by("document_type__title")

        _unid, _uaddr = _get_user_profile_data(request.user)

        return render(request, "customer_panel/complete_request.html", {
            "form": form,
            "cargo_request": cargo_request,
            "documents": documents,
            "doorstep_option": doorstep_option,
            "user_national_id": _unid,
            "user_phone": getattr(request.user, "mobile", ""),
            "user_address": _uaddr,
        })

    # ── GET ──
    else:
        form = OrderCompletionForm(instance=cargo_request, user=request.user)

    documents = OrderDocument.objects.select_related(
        "document_type"
    ).filter(order=cargo_request).order_by("document_type__title")

    _unid, _uaddr = _get_user_profile_data(request.user)

    return render(request, "customer_panel/complete_request.html", {
        "form": form,
        "cargo_request": cargo_request,
        "documents": documents,
        "doorstep_option": doorstep_option,
        "user_national_id": _unid,
        "user_phone": getattr(request.user, "mobile", ""),
        "user_address": _uaddr,
    })


# ════════════════════════════════════════════════════════════════
# AJAX Loaders
# ════════════════════════════════════════════════════════════════

def load_cargo_types(request):
    transport_mode = request.GET.get('transport_mode')
    if transport_mode:
        cargo_types = CargoType.objects.filter(
            transport_mode=transport_mode
        ).values('id', 'name')
        return JsonResponse(list(cargo_types), safe=False)
    return JsonResponse([], safe=False)


def load_cargo_subcategories(request):
    category_id = request.GET.get('category_id')
    if category_id:
        subs = CargoSubCategory.objects.filter(
            category_id=category_id
        ).values('id', 'name')
        return JsonResponse(list(subs), safe=False)
    return JsonResponse([], safe=False)


def load_subcategories(request):
    """لیست زیردسته‌های یک دسته اصلی (برای صفحه تکمیل سفارش)."""
    cargo_type_id = request.GET.get('cargo_type')
    try:
        cargo_type_id = int(cargo_type_id)
    except (ValueError, TypeError):
        return JsonResponse([], safe=False)
    subs = CargoSubCategory.objects.filter(
        category_id=cargo_type_id
    ).values('id', 'name')
    return JsonResponse(list(subs), safe=False)


def load_subcategory_children(request):
    """لیست فرزندهای یک زیردسته + گزینه ثابت «سایر»."""
    subcategory_id = request.GET.get('subcategory')
    try:
        subcategory_id = int(subcategory_id)
    except (ValueError, TypeError):
        return JsonResponse([], safe=False)
    children = list(
        CargoSubCategoryChild.objects.filter(
            subcategory_id=subcategory_id
        ).values('id', 'name')
    )
    children.append({'id': 'other', 'name': 'سایر (وارد کردن دستی)'})
    return JsonResponse(children, safe=False)


# ════════════════════════════════════════════════════════════════
# فاکتور PDF
# ════════════════════════════════════════════════════════════════

@login_required
def generate_order_invoice_pdf(request, order_id):
    import base64
    from pathlib import Path
    from django.contrib.staticfiles.finders import find as static_find
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration

    order = get_object_or_404(CargoRequest, id=order_id, customer=request.user)

    # ── فونت: base64 داخل CSS (مطمئن‌ترین روش روی Windows) ────
    font_css = ''
    font_path = static_find('fonts/BYekan.ttf')
    if font_path:
        font_b64 = base64.b64encode(Path(font_path).read_bytes()).decode()
        font_bold_path = static_find('fonts/BYekanBold.ttf')
        bold_b64 = ''
        if font_bold_path:
            bold_b64 = base64.b64encode(Path(font_bold_path).read_bytes()).decode()
        font_css = f"""
@font-face {{
    font-family: 'BYekan';
    src: url('data:font/truetype;base64,{font_b64}') format('truetype');
    font-weight: normal;
}}
"""
        if bold_b64:
            font_css += f"""
@font-face {{
    font-family: 'BYekan';
    src: url('data:font/truetype;base64,{bold_b64}') format('truetype');
    font-weight: bold;
}}
"""

    # ── CSS اصلی از disk ─────────────────────────────────────────
    css_main = ''
    css_path = static_find('css/pdf_invoice.css')
    if css_path:
        css_main = Path(css_path).read_text(encoding='utf-8')

    # ── لوگو base64 ─────────────────────────────────────────────
    logo_data_url = ''
    logo_path = (static_find('img/logo.jpeg') or
                 static_find('img/logo.jpg') or
                 static_find('img/logo.png'))
    if logo_path:
        ext = logo_path.rsplit('.', 1)[-1].lower()
        mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else 'image/png'
        logo_data_url = f'data:{mime};base64,{base64.b64encode(Path(logo_path).read_bytes()).decode()}'

    context = {
        'order': order,
        'today': timezone.now(),
        'css_content': css_main,
        'logo_data_url': logo_data_url,
    }
    html_string = render_to_string('orders/pdf/invoice_template.html', context)

    font_config = FontConfiguration()
    stylesheets = [CSS(string=font_css, font_config=font_config)] if font_css else []

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Invoice-{order.id}.pdf"'
    HTML(string=html_string).write_pdf(
        response,
        stylesheets=stylesheets,
        font_config=font_config,
    )
    return response


# ════════════════════════════════════════════════════════════════
# لغو سفارش پیش‌نویس
# ════════════════════════════════════════════════════════════════

@login_required
@require_POST
def cancel_draft_order(request, order_id):
    cargo_request = get_object_or_404(
        CargoRequest, id=order_id, customer=request.user,
    )

    if cargo_request.status != OrderStatus.DRAFT:
        messages.error(request, "فقط سفارش‌های پیش‌نویس قابل لغو هستند.")
        return redirect('customer:order_detail', pk=cargo_request.id)

    cargo_request.status = OrderStatus.CANCELLED
    cargo_request.save(update_fields=['status'])

    OrderHistory.objects.create(
        order=cargo_request,
        changed_by=request.user,
        note="سفارش توسط مشتری لغو شد."
    )

    messages.success(request, f"سفارش شماره {cargo_request.id} لغو شد.")
    return redirect('customer:order_detail', pk=cargo_request.id)


# ════════════════════════════════════════════════════════════════
# Cross-site entry (از Tejarat)
# ════════════════════════════════════════════════════════════════

def crosssite_order_entry(request):
    from django.urls import reverse
    from urllib.parse import urlencode

    token = request.GET.get('token', '').strip()

    if token:
        request.session['crosssite_token'] = token
    else:
        token = request.session.get('crosssite_token', '')

    if not token:
        messages.error(request, "لینک ورودی نامعتبر است.")
        return redirect('orders:create_request')

    if not request.user.is_authenticated:
        login_url = reverse('customer:login')
        next_path = reverse('orders:crosssite_order_entry')
        query = urlencode({'next': next_path})
        return redirect(f"{login_url}?{query}")

    from accounts.models import User as UserModel
    if request.user.role != UserModel.Role.CUSTOMER:
        request.session.pop('crosssite_token', None)
        messages.error(
            request,
            "ثبت سفارش فقط برای حساب‌های مشتری امکان‌پذیر است. "
            "لطفاً با یک حساب مشتری وارد شوید."
        )
        return redirect('orders:create_request')

    request.session.pop('crosssite_token', None)

    order_data = consume_order_token(token)

    if not order_data:
        messages.error(
            request,
            "لینک وارد شده منقضی شده یا قبلاً استفاده شده است. "
            "لطفاً دوباره از سایت بازرگانی استعلام بگیرید."
        )
        return redirect('orders:create_request')

    try:
        draft_order = _create_draft_from_crosssite(request.user, order_data)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"[CrossSite] Draft creation failed: {e}")
        messages.error(request, "خطا در ساخت سفارش. لطفاً دوباره تلاش کنید.")
        return redirect('orders:create_request')

    messages.success(request, "اطلاعات سفارش با موفقیت دریافت شد. لطفاً اطلاعات تکمیلی را وارد کنید.")
    return redirect('orders:complete_order_details', order_id=draft_order.id)


def _create_draft_from_crosssite(user, order_data: dict):
    from locations.models import City, Port

    rate = get_object_or_404(Rate, id=order_data['rate_id'], is_active=True)
    origin_city = get_object_or_404(City, id=order_data['origin_city'])
    destination_port = get_object_or_404(Port, id=order_data['destination_port'])
    cargo_type = get_object_or_404(CargoType, id=order_data['cargo_type'])

    transport_mode = order_data['transport_mode']
    shipping_procedure = order_data['shipping_procedure']
    is_fcl = transport_mode in ['sea_fcl', 'FCL']

    dimensions_data = [] if is_fcl else order_data.get('dimensions', [])

    calculation_payload = {
        'origin_city': origin_city,
        'destination_port': destination_port,
        'transport_mode': transport_mode,
        'shipping_procedure': shipping_procedure,
        'cargo_type': cargo_type,
        'actual_weight': order_data.get('actual_weight', 0),
        'needs_office_packaging': order_data.get('needs_office_packaging', False),
        'needs_onsite_packaging': order_data.get('needs_onsite_packaging', False),
        'needs_doorstep_packaging': order_data.get('needs_doorstep_packaging', False),
        'origin_id': origin_city.id,
        'destination_id': destination_port.id,
    }
    if is_fcl:
        calculation_payload['container_size'] = order_data.get('container_size')
        calculation_payload['container_type'] = order_data.get('container_type')
        calculation_payload['container_count'] = order_data.get('container_count', 1)

    match_data = calculate_and_match_rates(calculation_payload, dimensions_data)

    selected_result = None
    for item in match_data.get('results', []):
        if str(item['rate_id']) == str(order_data['rate_id']):
            selected_result = item
            break

    if not selected_result:
        raise ValueError("نرخ انتخاب‌شده در نتایج محاسبه یافت نشد (ممکن است منقضی شده باشد).")

    cargo_request = CargoRequest(
        customer=user,
        origin_city=origin_city,
        origin_province=origin_city.province if hasattr(origin_city, 'province') else None,
        destination_port=destination_port,
        transport_mode=transport_mode,
        shipping_procedure=shipping_procedure,
        cargo_type=cargo_type,
        actual_weight=order_data.get('actual_weight', 0),
        selected_rate=rate,
        status=OrderStatus.DRAFT,
        chargeable_weight=match_data.get('chargeable_weight', 0),
        base_shipping_price=selected_result.get('base_shipping_price', 0),
        office_packaging_price=selected_result.get('office_packaging_price', 0),
        onsite_packaging_price=selected_result.get('onsite_packaging_price', 0),
        doorstep_packaging_price=selected_result.get('doorstep_packaging_price', 0),
        vat_amount=selected_result.get('vat_amount', 0),
        price_subtotal=selected_result.get('subtotal', 0),
        final_price=selected_result.get('total_price', 0),
        needs_office_packaging=order_data.get('needs_office_packaging', False),
        needs_onsite_packaging=order_data.get('needs_onsite_packaging', False),
        needs_doorstep_packaging=order_data.get('needs_doorstep_packaging', False),
    )

    if is_fcl:
        cargo_request.container_size = order_data.get('container_size')
        cargo_request.container_type = order_data.get('container_type')
        cargo_request.container_count = order_data.get('container_count', 1)

    cargo_request.save()

    if not is_fcl:
        from .models import CargoDimension
        for dim in dimensions_data:
            try:
                CargoDimension.objects.create(
                    cargo_request=cargo_request,
                    length=float(dim['length']),
                    width=float(dim['width']),
                    height=float(dim['height']),
                    quantity=int(dim.get('quantity', 1)),
                )
            except (KeyError, TypeError, ValueError):
                continue

    OrderHistory.objects.create(
        order=cargo_request,
        changed_by=user,
        note="سفارش از طریق سایت بازرگانی Tejarat ایجاد شد و نرخ انتخاب گردید."
    )

    return cargo_request