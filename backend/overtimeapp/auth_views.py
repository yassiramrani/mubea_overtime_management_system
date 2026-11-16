from datetime import timedelta
from django.conf import settings
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.db import transaction, connection
from django.http import JsonResponse
from django.middleware.csrf import get_token
from rest_framework.authentication import SessionAuthentication
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .serializers import PasswordChangeSerializer


class LoginThrottle(AnonRateThrottle):
    scope = 'login'


class LoginView(ObtainAuthToken):
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = User.objects.select_for_update().get(pk=serializer.validated_data['user'].pk)
        token, _ = Token.objects.get_or_create(user=user)
        if token.created + timedelta(seconds=settings.AUTH_TOKEN_TTL_SECONDS) <= timezone.now():
            token.delete()
            token = Token.objects.create(user=user)
        return Response({'token': token.key})


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def session_csrf(request):
    response = Response({'csrfToken': get_token(request)})
    response['Cache-Control'] = 'no-store'
    return response


class BrowserLoginView(LoginView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        # DRF session auth only checks CSRF after authentication. Login needs an
        # explicit check as well, including for anonymous callers.
        SessionAuthentication().enforce_csrf(request)
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = User.objects.select_for_update().get(pk=serializer.validated_data['user'].pk)
        if not user.is_active or not user.check_password(serializer.validated_data['password']):
            return Response({'detail': 'Credentials changed. Sign in again.'}, status=400)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        request.session.set_expiry(settings.AUTH_TOKEN_TTL_SECONDS)
        response = Response({'authenticated': True})
        response['Cache-Control'] = 'no-store'
        return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sign_out(request):
    Token.objects.filter(user=request.user).delete()
    logout(request)
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def change_password(request):
    """Rotate the caller's password and token so other sessions are signed out."""
    serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    user = User.objects.select_for_update().get(pk=request.user.pk)
    user.set_password(serializer.validated_data['new_password'])
    user.save(update_fields=['password'])
    Token.objects.filter(user=user).delete()
    if isinstance(request.auth, Token):
        token = Token.objects.create(user=user)
        return Response({'token': token.key})
    update_session_auth_hash(request, user)
    return Response({'authenticated': True})


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})
