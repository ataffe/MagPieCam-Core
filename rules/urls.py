from rest_framework_nested import routers
from rules.views import RuleViewSet
from camera.urls import camera_router

app_name = 'rules'

rules_router = routers.NestedDefaultRouter(camera_router, r'cameras', lookup='camera')
rules_router.register(r'rules', RuleViewSet, basename='camera-rules')

urlpatterns = [
    *rules_router.urls,
]