from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


urlpatterns = [
    path('', include('core.urls')),
    path('admin/', admin.site.urls),
    path('rates/', include('rates.urls')), 
    path('panel/', include('panel.urls', namespace='forwarder_panel')),
    path('staff/', include('admin_dashboard.urls', namespace='staff_dashboard')),
    path('auth/', include('customer.urls', namespace='customer')),

    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # مسیر جدید برای اپلیکیشن سفارشات/درخواست‌های مشتری
    path('orders/', include('orders.urls', namespace='orders')), 
    path('locations/', include('locations.urls')),
    path('api/v1/orders/', include('orders.api.v1.urls')),
    path('api/v1/locations/', include('locations.api.v1.urls')),
    path('api/v1/accounts/', include('accounts.api.v1.urls')),
    path('api/v1/panel/', include('panel.api.v1.urls')),
    path('api/v1/rates/', include('rates.api.v1.urls')),
    path("forwarder/support/", include(("support.urls", "support"), namespace="forwarder_support")),
    path("customer/profile/support/", include(("support.urls", "support"), namespace="customer_support")),
    path("documents/", include("documents.urls")),


]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

