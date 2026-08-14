from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('v1/', include('rules.urls')),
    path('v1/', include('users.urls')),
    path('v1/', include('camera.urls')),
    path('v1/', include('notifications.urls')),
    path('api/schema', SpectacularAPIView.as_view(), name='schema'),
    path('api/swagger', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger'),
]
