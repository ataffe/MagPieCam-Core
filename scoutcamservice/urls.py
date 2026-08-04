from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('v1/', include('rules.urls')),
    path('v1/', include('users.urls')),
    path('v1/', include('camera.urls')),
    path('v1/', include('notifications.urls')),
]
