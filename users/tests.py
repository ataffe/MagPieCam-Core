import uuid

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import User

def make_user(username, email, password='StrongPass123!', first_name='Test', last_name='User'):
    return User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )

class UserTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123',
            first_name='Test',
            last_name='User',
        )

    def get_jwt_token(self, user):
        """Helper to generate a JWT token for a given user."""
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)

    def authenticate(self, user):
        """Helper to set the JWT token on the client."""
        token = self.get_jwt_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_delete_user_success(self):
        self.authenticate(self.user)
        response = self.client.delete(
            reverse('users:user_detail', kwargs={'public_user_id': self.user.public_user_id}),
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(public_user_id=self.user.public_user_id).exists())

    def test_delete_user_not_found(self):
        self.authenticate(self.user)
        response = self.client.delete(
            reverse('users:user_detail', kwargs={'public_user_id': uuid.uuid4()}),
        )
        self.assertEqual(response.status_code, 404)

    def test_get_user_success(self):
        self.authenticate(self.user)
        response = self.client.get(
            reverse('users:user_detail', kwargs={'public_user_id': self.user.public_user_id}),
        )
        self.assertEqual(response.status_code, 200)
        user_returned = response.json()
        self.assertEqual(user_returned['public_user_id'], str(self.user.public_user_id))

    def test_get_user_not_found(self):
        self.authenticate(self.user)
        response = self.client.get(
            reverse('users:user_detail', kwargs={'public_user_id': uuid.uuid4()}),
        )
        self.assertEqual(response.status_code, 404)

    def test_get_all_users(self):
        self.authenticate(self.user)
        User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpassword1232',
            first_name='Test2',
            last_name='User2',
        )
        response = self.client.get(
            reverse('users:user_list'),
        )
        self.assertEqual(response.status_code, 200)
        users_json = response.json()
        self.assertEqual(len(users_json), 2)

    def test_get_user_returns_correct_fields(self):
        self.authenticate(self.user)
        response = self.client.get(
            reverse('users:user_detail', kwargs={'public_user_id': self.user.public_user_id}),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['email'], self.user.email)
        self.assertEqual(data['first_name'], self.user.first_name)
        self.assertEqual(data['last_name'], self.user.last_name)
        self.assertNotIn('password', data)

    def test_get_other_users_profile_returns_404(self):
        other_user = make_user('other', 'other@example.com')
        self.authenticate(self.user)
        response = self.client.get(
            reverse('users:user_detail', kwargs={'public_user_id': other_user.public_user_id}),
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_other_users_profile_returns_404(self):
        other_user = make_user('other', 'other@example.com')
        self.authenticate(self.user)
        response = self.client.delete(
            reverse('users:user_detail', kwargs={'public_user_id': other_user.public_user_id}),
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(User.objects.filter(public_user_id=other_user.public_user_id).exists())

    def test_unauthenticated_get_user_returns_401(self):
        response = self.client.get(
            reverse('users:user_detail', kwargs={'public_user_id': self.user.public_user_id}),
        )
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_delete_user_returns_401(self):
        response = self.client.delete(
            reverse('users:user_detail', kwargs={'public_user_id': self.user.public_user_id}),
        )
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_user_list_returns_401(self):
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 401)

class UserAPNsTokenTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword123',
            first_name='Test',
            last_name='User',
        )

    def authenticate(self, user):
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

    def test_set_apns_token_success(self):
        self.authenticate(self.user)
        response = self.client.post(
            reverse('users:apns_token'),
            data={'apns_device_id': 'device-token-1'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.apns_device_id, 'device-token-1')

    def test_set_apns_token_updates_existing_token(self):
        self.authenticate(self.user)
        self.client.post(
            reverse('users:apns_token'),
            data={'apns_device_id': 'device-token-1'},
            format='json',
        )
        response = self.client.post(
            reverse('users:apns_token'),
            data={'apns_device_id': 'device-token-2'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.apns_device_id, 'device-token-2')

    def test_resubmitting_same_apns_token_succeeds(self):
        self.authenticate(self.user)
        self.client.post(
            reverse('users:apns_token'),
            data={'apns_device_id': 'device-token-1'},
            format='json',
        )
        response = self.client.post(
            reverse('users:apns_token'),
            data={'apns_device_id': 'device-token-1'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_set_apns_token_missing_returns_400(self):
        self.authenticate(self.user)
        response = self.client.post(
            reverse('users:apns_token'),
            data={},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_set_apns_token_blank_returns_400(self):
        self.authenticate(self.user)
        response = self.client.post(
            reverse('users:apns_token'),
            data={'apns_device_id': ''},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_set_apns_token_already_used_by_another_user_returns_400(self):
        other_user = make_user('other', 'other@example.com')
        other_user.apns_device_id = 'device-token-1'
        other_user.save()

        self.authenticate(self.user)
        response = self.client.post(
            reverse('users:apns_token'),
            data={'apns_device_id': 'device-token-1'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_set_apns_token_unauthenticated_returns_401(self):
        response = self.client.post(
            reverse('users:apns_token'),
            data={'apns_device_id': 'device-token-1'},
            format='json',
        )
        self.assertEqual(response.status_code, 401)

class RegisterTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_user_and_returns_tokens(self):
        payload = {
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'alice@example.com',
            'password': 'StrongPass123!',
        }
        response = self.client.post(reverse('users:register'), data=payload, format='json')
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertTrue(User.objects.filter(email='alice@example.com').exists())

    def test_register_duplicate_email_returns_400(self):
        make_user('alice', 'alice@example.com')
        payload = {
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'alice@example.com',
            'password': 'StrongPass123!',
        }
        response = self.client.post(reverse('users:register'), data=payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_register_missing_required_fields_returns_400(self):
        response = self.client.post(
            reverse('users:register'),
            data={'email': 'alice@example.com'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_register_returns_user_data_in_response(self):
        payload = {
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'alice@example.com',
            'password': 'StrongPass123!',
        }
        response = self.client.post(reverse('users:register'), data=payload, format='json')
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn('user', data)
        self.assertIn('public_user_id', data['user'])
        self.assertNotIn('password', data['user'])
        self.assertEqual(data['user']['username'], 'alice@example.com')

    def test_register_email_normalized_to_lowercase(self):
        payload = {
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'Alice@Example.COM',
            'password': 'StrongPass123!',
        }
        response = self.client.post(reverse('users:register'), data=payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(email='alice@example.com').exists())

    def test_register_weak_password_returns_400(self):
        payload = {
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'alice@example.com',
            'password': 'password',
        }
        response = self.client.post(reverse('users:register'), data=payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_register_invalid_email_format_returns_400(self):
        payload = {
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'not-an-email',
            'password': 'StrongPass123!',
        }
        response = self.client.post(reverse('users:register'), data=payload, format='json')
        self.assertEqual(response.status_code, 400)

class JWTAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_authenticate_user(self):
        payload = {
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'alice@example.com',
            'password': 'StrongPass123!',
        }
        response = self.client.post(reverse('users:register'), data=payload, format='json')
        self.assertEqual(response.status_code, 201)

        user_data = {
            "email": "alice@example.com",
            "password": "StrongPass123!",
        }
        response = self.client.post(reverse('users:token_obtain_pair'), data=user_data, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)

    def test_authenticate_wrong_password_returns_401(self):
        make_user('alice', 'alice@example.com')
        response = self.client.post(
            reverse('users:token_obtain_pair'),
            data={'email': 'alice@example.com', 'password': 'WrongPassword!'},
            format='json',
        )
        self.assertEqual(response.status_code, 401)

    def test_authenticate_nonexistent_user_returns_401(self):
        response = self.client.post(
            reverse('users:token_obtain_pair'),
            data={'email': 'nobody@example.com', 'password': 'StrongPass123!'},
            format='json',
        )
        self.assertEqual(response.status_code, 401)

    def test_refresh_token_returns_new_access_token(self):
        user = make_user('alice', 'alice@example.com')
        refresh = RefreshToken.for_user(user)
        response = self.client.post(
            reverse('users:token_refresh'),
            data={'refresh': str(refresh)},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.json())

    def test_invalid_token_on_protected_endpoint_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer notavalidtoken')
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 401)
