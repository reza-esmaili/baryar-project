from django.urls import include, path

from . import (
    views_ajax,
    views_branches,
    views_dashboard,
    views_documents,
    views_orders,
    views_rates,
    views_settings,
    views_staff,
)

app_name = 'forwarder_panel'

urlpatterns = [
    path('', views_dashboard.dashboard_view, name='dashboard'),

    # مدارک و مستندات فورواردر
    path('documents/', views_documents.documents_view, name='documents'),

    path('rates/', views_rates.rate_list_view, name='rate_list'),
    path('rates/add/', views_rates.rate_create_view, name='rate_create'),
    path('rates/toggle-status/<int:rate_id>/', views_rates.toggle_rate_status, name='toggle_rate_status'),
    path('rates/delete/<int:rate_id>/', views_rates.delete_rate, name='delete_rate'),
    path('rates/<int:pk>/', views_rates.RateDetailUpdateView.as_view(), name='rate_detail'),
    path('rates/ajax/load-cargo-types/', views_ajax.load_cargo_types, name='ajax_load_cargo_types'),
    path('rates/bulk-delete/', views_rates.rate_bulk_delete, name='rate_bulk_delete'),
    path('rates/download-template/', views_rates.download_rate_template_excel, name='rate_download_template'),
    path('rates/bulk-upload/', views_rates.upload_rate_excel, name='rate_bulk_upload'),

    # مسیرهای شعبه
    path('branches/', views_branches.branch_list_view, name='branch_list'),
    path('branches/add/', views_branches.branch_create_view, name='branch_create'),
    path('branches/<int:pk>/', views_branches.branch_update_view, name='branch_update'),
    path('branches/toggle-status/<int:pk>/', views_branches.toggle_branch_status, name='toggle_branch_status'),

    # مسیرهای کارمند
    path('staff/', views_staff.staff_list_view, name='staff_list'),
    path('staff/add/', views_staff.staff_create_view, name='staff_create'),
    path('staff/<int:staff_id>/edit/', views_staff.staff_edit_view, name='staff_edit'),
    path('staff/<int:staff_id>/delete/', views_staff.staff_delete_view, name='staff_delete'),
    path('staff/<int:staff_id>/toggle-active/', views_staff.staff_toggle_active_view, name='staff_toggle_active'),
    path('first-login-password/', views_staff.first_login_password_change, name='first_login_password_change'),

    path('ajax/load-cities/', views_ajax.load_cities, name='ajax_load_cities'),

    path('orders/', views_orders.order_list_view, name='order_list'),
    path('orders/<int:order_id>/', views_orders.order_detail_view, name='order_detail'),

    path('reports/sales-chart-data/', views_dashboard.get_sales_chart_data, name='get_sales_chart_data'),
    path('reports/', views_dashboard.report_view, name='report_page'),
    path('support/', include(('support.urls', 'support'), namespace='forwarder_support')),
    path("document/<int:doc_id>/status/", views_orders.update_document_status, name="update_document_status"),
    path("order/<int:order_id>/request-document/", views_orders.request_additional_document, name="request_additional_document"),
    path("order/<int:order_id>/send-message/", views_orders.send_order_message, name="send_order_message"),
    path("notifications/", views_orders.forwarder_notifications_api, name="notifications_api"),
    path("notifications/mark-read/", views_orders.forwarder_mark_notifications_read, name="mark_notifications_read"),

    # تنظیمات
    path("settings/", views_settings.settings_view, name="settings"),
    path("settings/roles/new/", views_settings.role_create_or_edit, name="role_create"),
    path("settings/roles/<int:role_id>/edit/", views_settings.role_create_or_edit, name="role_edit"),
    path("settings/roles/<int:role_id>/delete/", views_settings.role_delete, name="role_delete"),
    path("settings/upload-logo/", views_settings.upload_company_logo, name="upload_logo"),
    path("settings/change-password/", views_settings.change_password_view, name="change_password"),
]
