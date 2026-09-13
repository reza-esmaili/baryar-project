# admin_dashboard/decorators.py

from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from accounts.models import User


def is_platform_staff(user):
    return user.is_authenticated and (user.is_staff or user.role == User.Role.PLATFORM_ADMIN)


def platform_staff_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("customer:login")
        if not is_platform_staff(request.user):
            return HttpResponseForbidden("شما دسترسی مشاهده این صفحه را ندارید.")
        return view_func(request, *args, **kwargs)
    return _wrapped
