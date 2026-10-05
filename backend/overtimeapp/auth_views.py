from datetime import timedelta
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.db import transaction, connection
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
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
    token = Token.objects.create(user=user)
    return Response({'token': token.key})


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        return JsonResponse({'status': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok'})
