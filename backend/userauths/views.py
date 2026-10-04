import json
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.crypto import constant_time_compare

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.permissions import ensure_self_or_staff
from userauths.models import Profile, User
from userauths.serializer import MyTokenObtainPairSerializer, ProfileSerializer, RegisterSerializer

logger = logging.getLogger(__name__)

PASSWORD_RESET_PURPOSE = "password_reset"
PASSWORD_RESET_GENERIC_MESSAGE = "If an account exists for this email, a password reset link has been sent."


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_scope = "auth"


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer
    throttle_scope = "auth"


@api_view(['GET'])
@permission_classes([AllowAny])
def getRoutes(request):
    routes = [
        '/api/token/',
        '/api/register/',
        '/api/token/refresh/',
        '/api/test/'
    ]
    return Response(routes)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def testEndPoint(request):
    if request.method == 'GET':
        data = f"Congratulations {request.user}, your API just responded to a GET request."
        return Response({'response': data}, status=status.HTTP_200_OK)
    elif request.method == 'POST':
        try:
            body = request.body.decode('utf-8')
            data = json.loads(body)
            if 'text' not in data:
                return Response("Invalid JSON data", status=status.HTTP_400_BAD_REQUEST)
            text = data.get('text')
            data = f'Congratulations, your API just responded to a POST request with text: {text}'
            return Response({'response': data}, status=status.HTTP_200_OK)
        except json.JSONDecodeError:
            return Response("Invalid JSON data", status=status.HTTP_400_BAD_REQUEST)
    return Response("Invalid JSON data", status=status.HTTP_400_BAD_REQUEST)


class ProfileView(generics.RetrieveAPIView):
    """The signed-in user's own profile. Staff may read any profile."""

    permission_classes = (IsAuthenticated,)
    serializer_class = ProfileSerializer

    def get_object(self):
        user_id = ensure_self_or_staff(self.request, self.kwargs['user_id'])
        profile, _created = Profile.objects.get_or_create(user_id=user_id)
        return profile


def generate_numeric_otp(length=7):
    """Cryptographically random numeric OTP."""
    return ''.join(secrets.choice('0123456789') for _ in range(length))


def _build_reset_token(user):
    token = AccessToken.for_user(user)
    token.set_exp(lifetime=timedelta(minutes=settings.PASSWORD_RESET_TOKEN_MINUTES))
    token['purpose'] = PASSWORD_RESET_PURPOSE
    return str(token)


class PasswordEmailVerify(APIView):
    """
    Starts a password reset. Always returns the same response whether or not the email
    exists, and never returns any account data.
    """

    permission_classes = (AllowAny,)
    throttle_scope = "otp"

    def get(self, request, *args, **kwargs):
        email = (self.kwargs.get('email') or '').strip()
        user = User.objects.filter(email__iexact=email).first() if email else None

        if user is not None and user.is_active:
            user.otp = generate_numeric_otp()
            user.reset_token = _build_reset_token(user)
            user.save(update_fields=['otp', 'reset_token'])

            link = (
                f"{settings.SITE_URL}/create-new-password"
                f"?otp={user.otp}&uidb64={user.pk}&reset_token={user.reset_token}"
            )
            merge_data = {'link': link, 'username': user.username}
            subject = "Password Reset Request"
            text_body = render_to_string("email/password_reset.txt", merge_data)
            html_body = render_to_string("email/password_reset.html", merge_data)
            try:
                msg = EmailMultiAlternatives(
                    subject=subject, from_email=settings.FROM_EMAIL,
                    to=[user.email], body=text_body
                )
                msg.attach_alternative(html_body, "text/html")
                msg.send()
            except Exception:
                logger.exception("password reset email could not be sent for user %s", user.pk)

        return Response({"message": PASSWORD_RESET_GENERIC_MESSAGE}, status=status.HTTP_200_OK)


class PasswordChangeView(APIView):
    """
    Completes a password reset. Requires the user id, the OTP and the signed, unexpired,
    single-use reset token that were issued together.
    """

    permission_classes = (AllowAny,)
    throttle_scope = "otp"

    INVALID = {"message": "This password reset link is invalid or has expired."}

    def post(self, request, *args, **kwargs):
        payload = request.data
        otp = str(payload.get('otp') or '')
        uidb64 = str(payload.get('uidb64') or '')
        reset_token = str(payload.get('reset_token') or '')
        password = payload.get('password') or ''

        if not (otp and uidb64 and reset_token and password):
            return Response(self.INVALID, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=int(uidb64))
        except (User.DoesNotExist, ValueError):
            return Response(self.INVALID, status=status.HTTP_400_BAD_REQUEST)

        if not user.otp or not user.reset_token:
            return Response(self.INVALID, status=status.HTTP_400_BAD_REQUEST)
        if not constant_time_compare(otp, user.otp) or not constant_time_compare(reset_token, user.reset_token):
            return Response(self.INVALID, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = AccessToken(reset_token)
        except TokenError:
            return Response(self.INVALID, status=status.HTTP_400_BAD_REQUEST)
        if token.get('purpose') != PASSWORD_RESET_PURPOSE or str(token.get('user_id')) != str(user.pk):
            return Response(self.INVALID, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(password, user=user)
        except DjangoValidationError as exc:
            return Response({"message": " ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.otp = ""
        user.reset_token = ""
        user.save()
        return Response({"message": "Password Changed Successfully"}, status=status.HTTP_201_CREATED)
