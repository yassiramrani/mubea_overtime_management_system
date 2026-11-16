from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


@override_settings(SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class BrowserSessionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('browser-user', password='Browser-Initial-2026!')

    def csrf(self, client):
        response = client.get('/api/auth/session/csrf/')
        self.assertEqual(response['Cache-Control'], 'no-store')
        return response.data['csrfToken']

    def login(self, client):
        response = client.post('/api/auth/session/login/', {'username': self.user.username,
            'password': 'Browser-Initial-2026!'}, format='json', HTTP_X_CSRFTOKEN=self.csrf(client))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('token', response.data)
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]['httponly'])
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]['samesite'], 'Lax')

    def test_anonymous_login_and_authenticated_mutations_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.post('/api/auth/session/login/', {'username': self.user.username,
            'password': 'Browser-Initial-2026!'}, format='json').status_code, 403)
        self.login(client)
        self.assertEqual(client.get('/api/users/me/').status_code, 200)
        self.assertEqual(client.post('/api/auth/logout/').status_code, 403)
        self.assertEqual(client.post('/api/auth/logout/', HTTP_X_CSRFTOKEN=self.csrf(client)).status_code, 204)
        self.assertEqual(client.get('/api/users/me/').status_code, 401)

    def test_password_rotation_preserves_current_browser_and_revokes_other_sessions_and_tokens(self):
        current, other = APIClient(enforce_csrf_checks=True), APIClient(enforce_csrf_checks=True)
        self.login(current)
        self.login(other)
        token = Token.objects.create(user=self.user)
        changed = current.post('/api/auth/change-password/', {'current_password': 'Browser-Initial-2026!',
            'new_password': 'Browser-Replacement-2026!'}, format='json', HTTP_X_CSRFTOKEN=self.csrf(current))
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertNotIn('token', changed.data)
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())
        self.assertEqual(current.get('/api/users/me/').status_code, 200)
        self.assertEqual(other.get('/api/users/me/').status_code, 401)
        self.user.refresh_from_db()
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertEqual(current.get('/api/users/me/').status_code, 401)
