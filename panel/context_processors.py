from accounts.models import User

_PERM_FIELDS = [
    "can_view_orders", "can_manage_orders", "can_update_order_status",
    "can_send_order_message", "can_request_documents",
    "can_view_rates", "can_create_rates", "can_edit_rates",
    "can_delete_rates", "can_bulk_upload_rates",
    "can_view_land_requests", "can_accept_land_requests",
    "can_view_branches", "can_manage_branches",
    "can_view_staff", "can_manage_staff",
    "can_view_reports", "can_export_reports",
    "can_view_documents", "can_manage_documents",
    "can_view_support", "can_reply_support",
    "can_view_settings", "can_manage_roles", "can_upload_logo",
]

_FORWARDER_ROLES = (
    User.Role.FORWARDER_ADMIN,
    User.Role.FORWARDER_EXPERT,
    User.Role.FORWARDER_FINANCE,
)


def forwarder_permissions(request):
    """
    fw_perms را برای همه template‌های پنل فورواردر فراهم می‌کند.
    ادمین: همه True | کارمند: از نقش تعریف‌شده | بقیه: خالی
    """
    user = request.user
    if not user.is_authenticated or user.role not in _FORWARDER_ROLES:
        return {}

    from panel.decorators import get_company_for_user

    company = get_company_for_user(user)
    # منوی پنل بر اساس دسته‌های خدمات شرکت و وضعیت تایید/فعال بودن آن ساخته می‌شود:
    # تا شرکت تایید و فعال نشده، فقط بخش مدارک و ثبت‌نام در دسترس است.
    context = {
        'fw_company': company,
        'fw_company_ready': bool(company and company.is_operational),
        'fw_offers_land': bool(company and company.offers_land),
        'fw_offers_rates': bool(company and company.offers_rates),
    }

    if user.role == User.Role.FORWARDER_ADMIN:
        context['fw_perms'] = {f: True for f in _PERM_FIELDS}
        return context

    staff = getattr(user, 'forwarder_staff', None)
    if staff and staff.role:
        context['fw_perms'] = {f: bool(getattr(staff.role, f, False)) for f in _PERM_FIELDS}
    else:
        context['fw_perms'] = {f: False for f in _PERM_FIELDS}
    return context
