from rest_framework import serializers
from users.models import User
from django.contrib.auth.password_validation import validate_password

class UserSerializer(serializers.ModelSerializer):
    public_user_id = serializers.UUIDField(read_only=True)
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'public_user_id']

class RegisterUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with that email already exists.')
        return value.lower()

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )

class UserAPNsTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['apns_token']
        extra_kwargs = {'apns_token': {'required': True, 'allow_blank': False}}
