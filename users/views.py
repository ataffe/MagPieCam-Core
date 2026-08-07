from django.http import JsonResponse
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema

from users.models import User
from users.serializers import (
    RegisterUserSerializer, UserSerializer, UserAPNsTokenSerializer, MessageResponseSerializer)
from rest_framework.parsers import JSONParser

class RegisterUserView(generics.CreateAPIView):
    """Create a new user account and return JWT access/refresh tokens for it."""
    serializer_class = RegisterUserSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        token = RefreshToken.for_user(user)

        return JsonResponse({
            'user': {
                'public_user_id': str(user.public_user_id),
                'username': user.email,
            },
            'access': str(token.access_token),
            'refresh': str(token),
        }, status=status.HTTP_201_CREATED)

class UserView(generics.RetrieveDestroyAPIView):
    """Retrieve or delete the authenticated user's own account."""
    serializer_class = UserSerializer
    lookup_field = 'public_user_id'
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return User.objects.filter(public_user_id=self.request.user.public_user_id)

class UserListView(generics.ListAPIView):
    """List registered users."""
    serializer_class = UserSerializer
    queryset = User.objects.all()[:25]
    permission_classes = [permissions.IsAuthenticated]

class UserAPNsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]
    serializer_class = UserAPNsTokenSerializer

    @extend_schema(responses={200: MessageResponseSerializer})
    def post(self, request):
        """Register or update the authenticated user's APNs device token for push notifications."""
        serializer = UserAPNsTokenSerializer(instance=request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return JsonResponse({'message': 'APNs token updated successfully'}, status=status.HTTP_200_OK)
