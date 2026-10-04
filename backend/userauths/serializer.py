from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.serializers import PublicUserSerializer
from userauths.models import Profile, User


# Define a custom serializer that inherits from TokenObtainPairSerializer
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    '''
    Adds non-sensitive profile claims to the JWT so the frontend can render the user's name
    and decide whether to show the owner dashboard without an extra request.
    '''
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token['full_name'] = user.full_name
        token['email'] = user.email
        token['username'] = user.username
        # Lets the storefront show the "Admin" link to staff only. A convenience, not the
        # protection: every owner endpoint still checks is_staff on the server (IsStaffOwner).
        token['is_staff'] = bool(user.is_staff)
        try:
            token['vendor_id'] = user.vendor.id
        except Exception:
            token['vendor_id'] = 0

        return token


# Define a serializer for user registration, which inherits from serializers.ModelSerializer
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('full_name', 'email', 'phone', 'password', 'password2')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        user = User.objects.create(
            full_name=validated_data['full_name'],
            email=validated_data['email'],
            phone=validated_data['phone']
        )
        email_username, _domain = user.email.split('@')
        user.username = email_username
        user.set_password(validated_data['password'])
        user.save()
        return user


class UserSerializer(serializers.ModelSerializer):
    """
    The signed-in user's own account data. Never includes password, OTP, reset token,
    permission flags or group membership.
    """

    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'full_name', 'phone')
        read_only_fields = ('id', 'email')


class ProfileSerializer(serializers.ModelSerializer):

    class Meta:
        model = Profile
        fields = '__all__'
        read_only_fields = ('user', 'pid', 'date')

    def to_representation(self, instance):
        response = super().to_representation(instance)
        response['user'] = UserSerializer(instance.user).data
        return response


class PublicProfileSerializer(serializers.ModelSerializer):
    """What other shoppers may see about a reviewer."""

    user = PublicUserSerializer(read_only=True)

    class Meta:
        model = Profile
        fields = ('id', 'full_name', 'image', 'user')
        read_only_fields = fields


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
