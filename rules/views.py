from rest_framework.exceptions import PermissionDenied

from rules.models import Camera, Rule
from rules.serializers import RuleSerializer
from rest_framework import permissions, viewsets
from drf_spectacular.utils import extend_schema, extend_schema_view


@extend_schema_view(
    list=extend_schema(
        summary='List rules',
        description='List detection rules for a camera owned by the authenticated user.',
    ),
    retrieve=extend_schema(
        summary='Retrieve a rule',
        description='Retrieve a single detection rule for a camera owned by the authenticated user.',
    ),
    create=extend_schema(
        summary='Create a rule',
        description='Create a new detection rule for a camera owned by the authenticated user.',
    ),
    update=extend_schema(
        summary='Update a rule',
        description="Update a rule's writable fields (`rule`, `rule_nickname`, `is_enabled`, `last_triggered`).",
    ),
    partial_update=extend_schema(
        summary='Partially update a rule',
        description="Partially update a rule's writable fields "
                    "(`rule`, `rule_nickname`, `is_enabled`, `last_triggered`).",
    ),
    destroy=extend_schema(
        summary='Delete a rule',
        description='Delete a detection rule for a camera owned by the authenticated user.',
    ),
)
class RuleViewSet(viewsets.ModelViewSet):
    serializer_class = RuleSerializer
    lookup_field = 'public_rule_id'
    permission_classes = [permissions.IsAuthenticated]

    def get_camera(self):
        camera = Camera.objects.filter(
            public_camera_id=self.kwargs['camera_public_camera_id'],
            owner=self.request.user
        ).first()

        if camera is None:
            raise PermissionDenied('Camera not found or does not belong to this user')
        return camera

    def get_queryset(self):
        return Rule.objects.filter(camera=self.get_camera())

    def perform_create(self, serializer):
        serializer.save(camera=self.get_camera(), owner=self.request.user)
