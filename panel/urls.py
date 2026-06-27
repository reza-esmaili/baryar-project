from django.urls import path
from . import views
from django.urls import path, include

app_name = 'forwarder_panel'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),

    # مدارک و مستندات فورواردر
    path('documents/', views.documents_view, name='documents'),

    path('rates/', views.rate_list_view, name='rate_list'),
    path('rates/add/', views.rate_create_view, name='rate_create'),
    path('rates/toggle-status/<int:rate_id>/', views.toggle_rate_status, name='toggle_rate_status'),
    path('rates/delete/<int:rate_id>/', views.delete_rate, name='delete_rate'),
    path('rates/<int:pk>/', views.RateDetailUpdateView.as_view(), name='rate_detail'),
    path('rates/ajax/load-cargo-types/', views.load_cargo_types, name='ajax_load_cargo_types'),
    path('rates/bulk-delete/', views.rate_bulk_delete, name='rate_bulk_delete'),
    path('rates/download-template/', views.download_rate_template_excel, name='rate_download_template'),
    path('rates/bulk-upload/', views.upload_rate_excel, name='rate_bulk_upload'),

    # مسیرهای شعبه
    path('branches/', views.branch_list_view, name='branch_list'),
    path('branches/add/', views.branch_create_view, name='branch_create'),
    path('branches/<int:pk>/', views.branch_update_view, name='branch_update'),
    path('branches/toggle-status/<int:pk>/', views.toggle_branch_status, name='toggle_branch_status'),

    # مسیرهای کارمند
    path('staff/', views.staff_list_view, name='staff_list'),
    path('staff/add/', views.staff_create_view, name='staff_create'),
    path('staff/<int:staff_id>/edit/', views.staff_edit_view, name='staff_edit'),
    path('staff/<int:staff_id>/delete/', views.staff_delete_view, name='staff_delete'),
    path('staff/<int:staff_id>/toggle-active/', views.staff_toggle_active_view, name='staff_toggle_active'),
    path('first-login-password/', views.first_login_password_change, name='first_login_password_change'),

    path('ajax/load-cities/', views.load_cities, name='ajax_load_cities'),

    path('orders/', views.order_list_view, name='order_list'),
    path('orders/<int:order_id>/', views.order_detail_view, name='order_detail'),

    path('reports/sales-chart-data/', views.get_sales_chart_data, name='get_sales_chart_data'),
    path('reports/', views.report_view, name='report_page'),
    path('support/', include(('support.urls', 'support'), namespace='forwarder_support')),
    path("document/<int:doc_id>/status/",views.update_document_status,name="update_document_status"),
    path("order/<int:order_id>/request-document/",views.request_additional_document,name="request_additional_document"),
    path("order/<int:order_id>/send-message/", views.send_order_message, name="send_order_message"),
    path("notifications/", views.forwarder_notifications_api, name="notifications_api"),
    path("notifications/mark-read/", views.forwarder_mark_notifications_read, name="mark_notifications_read"),

    # تنظیمات
    path("settings/", views.settings_view, name="settings"),
    path("settings/roles/new/", views.role_create_or_edit, name="role_create"),
    path("settings/roles/<int:role_id>/edit/", views.role_create_or_edit, name="role_edit"),
    path("settings/roles/<int:role_id>/delete/", views.role_delete, name="role_delete"),
    path("settings/upload-logo/", views.upload_company_logo, name="upload_logo"),
    path("settings/change-password/", views.change_password_view, name="change_password"),
]
