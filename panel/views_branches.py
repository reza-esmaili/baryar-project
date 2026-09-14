import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from forwarders.models import ForwarderBranch

from .decorators import forwarder_required, get_company_for_user, staff_permission_required
from .forms import BranchForm


@login_required
@forwarder_required
@staff_permission_required('can_view_branches')
def branch_list_view(request):
    company = get_company_for_user(request.user)
    branches = ForwarderBranch.objects.filter(company=company).order_by('-created_at')
    return render(request, 'forwarder_panel/branch_list.html', {'branches': branches})


@login_required
@forwarder_required
@staff_permission_required('can_manage_branches')
def branch_create_view(request):
    company = get_company_for_user(request.user)
    if request.method == 'POST':
        form = BranchForm(request.POST)
        if form.is_valid():
            form.save(forwarder_company=company)
            messages.success(request, "شعبه با موفقیت افزوده شد.")
            return redirect('forwarder_panel:branch_list')
    else:
        form = BranchForm()
    return render(request, 'forwarder_panel/branch_form.html', {'form': form})


@login_required
@forwarder_required
@staff_permission_required('can_manage_branches')
def branch_update_view(request, pk):
    company = get_company_for_user(request.user)
    branch = get_object_or_404(ForwarderBranch, pk=pk, company=company)

    if request.method == 'POST':
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            form.save(forwarder_company=company)
            messages.success(request, "تغییرات شعبه ذخیره شد.")
            return redirect('forwarder_panel:branch_list')
    else:
        form = BranchForm(instance=branch)
    return render(request, 'forwarder_panel/branch_form.html', {'form': form, 'branch': branch})


@login_required
@forwarder_required
@staff_permission_required('can_manage_branches')
@require_POST
def toggle_branch_status(request, pk):
    company = get_company_for_user(request.user)
    branch = get_object_or_404(ForwarderBranch, pk=pk, company=company)
    data = json.loads(request.body)
    branch.is_active = data.get('is_active', False)
    branch.save()
    return JsonResponse({'success': True, 'is_active': branch.is_active})
