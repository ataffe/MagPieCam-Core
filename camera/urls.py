from rest_framework_nested import routers
from django.urls import path

from camera.views import (
    CameraViewSet,
    PresignedImageUploadUrlView,
    CameraPreviewTimeView,
    ProvisionCameraView,
    CameraRegistrationView,
    CameraClaimView,
    CameraTokenExchangeView,
    MediaMtxAuthView
)

app_name = 'camera'

camera_router = routers.DefaultRouter()
camera_router.register(r'cameras', CameraViewSet, basename='camera')

urlpatterns = [
    # These must come before the router's URLs: the router's detail route
    # (cameras/<public_camera_id>/) is greedy and would otherwise swallow
    # cameras/provision/, cameras/register/, and cameras/claim/ as lookups.
    path('cameras/presigned_upload_url/', PresignedImageUploadUrlView.as_view(), name='presigned_upload'),
    path('cameras/update_preview_time/', CameraPreviewTimeView.as_view(), name='update_preview_time'),
    path('cameras/provision/', ProvisionCameraView.as_view(), name='create_camera'),
    path('cameras/register/', CameraRegistrationView.as_view(), name='register_camera'),
    path('cameras/claim/', CameraClaimView.as_view(), name='claim_camera'),
    path('cameras/auth/token/', CameraTokenExchangeView.as_view(), name='token_exchange'),
    path('cameras/mediamtx/auth/', MediaMtxAuthView.as_view(), name='mediamtx_auth'),
    *camera_router.urls,
]