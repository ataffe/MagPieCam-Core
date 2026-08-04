from rest_framework_nested import routers
from notifications.views import NotificationViewSet
from camera.urls import camera_router

app_name = 'notifications'

notification_router = routers.NestedDefaultRouter(camera_router, r'cameras', lookup='public_camera_id')
notification_router.register(r'notifications', NotificationViewSet, basename='camera-notifications')

urlpatterns = [
    *notification_router.urls,
]