import uuid
from urllib.parse import urlparse, parse_qs

from rest_framework import viewsets
from rest_framework.exceptions import ParseError
from rest_framework.pagination import CursorPagination
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema_view, extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from notifications.models import Notification
from notifications.serializers import NotificationSerializer
from camera.models import Camera

class NotificationPagination(CursorPagination):
    page_size = 10
    max_page_size = 100
    cursor_query_param = 'cursor'
    ordering = '-public_notification_id'

    def encode_cursor(self, cursor):
        """Return the bare cursor token instead of a full next/previous URL.

        Delegates to DRF for the actual offset/reverse/position -> base64
        encoding and only strips the URL wrapper off the result, so this stays
        correct if DRF's internal cursor format ever changes. The client
        resends the token as-is via `?cursor=<token>`; a bare token also
        avoids baking this server's scheme/host into the response, which
        matters behind a reverse proxy that changes either.
        """
        url = super().encode_cursor(cursor)
        query = parse_qs(urlparse(url).query)
        return query[self.cursor_query_param][0]

    def get_paginated_response_schema(self, schema):
        # next/previous are bare cursor tokens now, not URLs -- the parent's
        # schema advertises `format: uri`, which would be wrong here.
        response_schema = super().get_paginated_response_schema(schema)
        for field in ('next', 'previous'):
            response_schema['properties'][field].pop('format', None)
            response_schema['properties'][field]['example'] = 'cD00ODY='
        return response_schema

@extend_schema_view(
    list=extend_schema(
        summary="List notifications for a camera",
        description="List notifications for a camera owned by the authenticated user.",
        parameters=[
                OpenApiParameter(
                    name="since",
                    type=OpenApiTypes.UUID,
                    location=OpenApiParameter.QUERY,
                    required=False,
                    description="Return only notifications newer than this notification's public ID.",
                )
            ]
    )
)
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """List or retrieve notifications for a camera owned by the authenticated user."""
    serializer_class = NotificationSerializer
    lookup_field = "public_notification_id"
    pagination_class = NotificationPagination

    @staticmethod
    def _is_uuid7(unverified_uuid):
        try:
            val = uuid.UUID(unverified_uuid)
            return val.version == 7
        except ValueError:
            return False

    def get_queryset(self):
        camera = get_object_or_404(
            Camera,
            public_camera_id=self.kwargs["camera_public_camera_id"],
            owner=self.request.user,
        )
        qs = Notification.objects.filter(camera=camera).select_related('rule')

        if self.action == "list":
            since = self.request.query_params.get("since")
            if since is not None:
                if not self._is_uuid7(since):
                    raise ParseError("'since' must be a valid UUIDv7.")
                qs = qs.filter(public_notification_id__gt=since)

        return qs.order_by("-public_notification_id")
