import hashlib
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import User
from camera.models import Camera
from camera.s3_client import get_s3_client
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken

DEVICE_ID = '1234567890ABCDEF'


def camera_access_token(camera):
    token = AccessToken()
    token['public_camera_id'] = str(camera.public_camera_id)
    token['scope'] = 'camera'
    return str(token)

def make_user(username, email, password='StrongPass123!', first_name='Test', last_name='User', is_staff=False):
    return User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        is_staff=is_staff,
    )

class CameraTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('alice', 'alice@example.com', first_name='Alice', last_name='Smith')
        self.other_user = make_user('bob', 'bob@example.com', first_name='Bob', last_name='Jones')
        self.authenticate(user=self.user)
        self.camera = Camera.objects.create(owner=self.user, location='Front door')
    
    def get_jwt_token(self, user):
        """Helper to generate a JWT token for a given user."""
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)
    
    def authenticate(self, user):
        """Helper to set the JWT token on the client."""
        token = self.get_jwt_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_list_cameras_returns_only_owned(self):
        Camera.objects.create(owner=self.other_user, location='Garage')
        response = self.client.get(reverse('camera:camera-list'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['location'], 'Front door')

    def test_create_camera_returns_201_and_persists(self):
        payload = {'location': 'Back yard'}
        response = self.client.post(reverse('camera:camera-list'), data=payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Camera.objects.filter(location='Back yard', owner=self.user).exists())

    def test_create_camera_missing_required_fields_returns_400(self):
        response = self.client.post(reverse('camera:camera-list'), data={}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_get_camera_returns_correct_data(self):
        response = self.client.get(
            reverse('camera:camera-detail', kwargs={'public_camera_id': self.camera.public_camera_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['location'], 'Front door')

    def test_get_camera_preview_url_is_null_when_no_preview_uploaded(self):
        response = self.client.get(
            reverse('camera:camera-detail', kwargs={'public_camera_id': self.camera.public_camera_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['camera_preview_url'])

    @patch('camera.serializers.get_camera_preview_download_url')
    def test_get_camera_preview_url_is_populated_after_preview_uploaded(self, mock_get_url):
        mock_get_url.return_value = 'https://example.com/preview.jpg'
        self.camera.preview_updated_at = timezone.now()
        self.camera.save()

        response = self.client.get(
            reverse('camera:camera-detail', kwargs={'public_camera_id': self.camera.public_camera_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['camera_preview_url'], 'https://example.com/preview.jpg')
        mock_get_url.assert_called_once_with(f'preview/{self.camera.public_camera_id}/latest.jpg')

    def test_patch_camera_cannot_set_preview_updated_at(self):
        response = self.client.patch(
            reverse('camera:camera-detail', kwargs={'public_camera_id': self.camera.public_camera_id}),
            data={'preview_updated_at': '2020-01-01T00:00:00Z'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.camera.refresh_from_db()
        self.assertIsNone(self.camera.preview_updated_at)

    def test_get_other_users_camera_returns_404(self):
        other_camera = Camera.objects.create(owner=self.other_user, location='Garage')
        response = self.client.get(
            reverse('camera:camera-detail', kwargs={'public_camera_id': other_camera.public_camera_id})
        )
        self.assertEqual(response.status_code, 404)

    def test_update_camera_location(self):
        response = self.client.patch(
            reverse('camera:camera-detail', kwargs={'public_camera_id': self.camera.public_camera_id}),
            data={'location': 'Side gate'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.camera.refresh_from_db()
        self.assertEqual(self.camera.location, 'Side gate')

    def test_delete_camera_returns_204_and_removes_record(self):
        response = self.client.delete(
            reverse('camera:camera-detail', kwargs={'public_camera_id': self.camera.public_camera_id})
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Camera.objects.filter(pk=self.camera.pk).exists())

    def test_unauthenticated_access_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse('camera:camera-list'))
        self.assertEqual(response.status_code, 401)

    def test_list_returns_empty_when_user_has_no_cameras(self):
        Camera.objects.filter(owner=self.user).delete()
        response = self.client.get(reverse('camera:camera-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_staff_user_with_all_true_sees_all_cameras(self):
        staff_user = make_user('carol', 'carol@example.com', first_name='Carol', last_name='Doe', is_staff=True)
        Camera.objects.create(owner=self.other_user, location='Garage')
        self.authenticate(user=staff_user)

        response = self.client.get(reverse('camera:camera-list'), {'all': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_staff_user_without_all_param_sees_only_owned(self):
        staff_user = make_user('carol', 'carol@example.com', first_name='Carol', last_name='Doe', is_staff=True)
        Camera.objects.create(owner=self.other_user, location='Garage')
        self.authenticate(user=staff_user)

        response = self.client.get(reverse('camera:camera-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_non_staff_user_with_all_true_still_filtered_to_owned(self):
        Camera.objects.create(owner=self.other_user, location='Garage')

        response = self.client.get(reverse('camera:camera-list'), {'all': 'true'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['location'], 'Front door')

    def test_create_response_includes_public_camera_id(self):
        payload = {'location': 'Driveway'}
        response = self.client.post(reverse('camera:camera-list'), data=payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('public_camera_id', response.json())

    def test_create_ignores_owner_in_payload(self):
        payload = {'location': 'Lobby', 'owner': self.other_user.pk}
        response = self.client.post(reverse('camera:camera-list'), data=payload, format='json')
        self.assertEqual(response.status_code, 201)
        camera = Camera.objects.get(location='Lobby')
        self.assertEqual(camera.owner, self.user)

    def test_update_other_users_camera_returns_404(self):
        other_camera = Camera.objects.create(owner=self.other_user, location='Garage')
        response = self.client.patch(
            reverse('camera:camera-detail', kwargs={'public_camera_id': other_camera.public_camera_id}),
            data={'location': 'Hacked'},
            format='json',
        )
        self.assertEqual(response.status_code, 404)
        other_camera.refresh_from_db()
        self.assertEqual(other_camera.location, 'Garage')

    def test_delete_other_users_camera_returns_404(self):
        other_camera = Camera.objects.create(owner=self.other_user, location='Garage')
        response = self.client.delete(
            reverse('camera:camera-detail', kwargs={'public_camera_id': other_camera.public_camera_id})
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Camera.objects.filter(pk=other_camera.pk).exists())

    def test_location_exceeds_max_length_returns_400(self):
        payload = {'location': 'A' * 101}
        response = self.client.post(reverse('camera:camera-list'), data=payload, format='json')
        self.assertEqual(response.status_code, 400)


class CameraProvisioningFlowTests(TestCase):
    """Covers the provision -> register -> claim device onboarding pipeline."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='StrongPass123!',
            first_name='Alice', last_name='Smith',
        )

    def authenticate(self, user):
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

    def provision(self, device_id=DEVICE_ID):
        return self.client.post(reverse('camera:create_camera'), data={'device_id': device_id}, format='json')

    def register(self, device_id, claim_token):
        return self.client.post(
            reverse('camera:register_camera'),
            data={'device_id': device_id, 'claim_token': claim_token},
            format='json',
        )

    def claim(self, claim_token, location='Front door'):
        return self.client.post(
            reverse('camera:claim_camera'),
            data={'claim_token': claim_token, 'location': location},
            format='json',
        )

    # --- Provision ---

    def test_provision_camera_returns_201_and_claim_token(self):
        response = self.provision()
        self.assertEqual(response.status_code, 201)
        claim_token = response.json()['claim_token']
        self.assertTrue(claim_token.startswith(f'{DEVICE_ID}_'))
        camera = Camera.objects.get(device_id=DEVICE_ID)
        self.assertFalse(camera.claimed)
        self.assertIsNone(camera.owner)
        self.assertEqual(
            camera.claim_token_hash,
            hashlib.sha256(claim_token.encode('utf-8')).hexdigest(),
        )

    def test_provision_camera_invalid_device_id_length_returns_400(self):
        response = self.provision(device_id='tooshort')
        self.assertEqual(response.status_code, 400)

    def test_provision_duplicate_device_id_returns_409(self):
        self.provision()
        response = self.provision()
        self.assertEqual(response.status_code, 409)

    # --- Register ---

    def test_register_camera_returns_201_and_device_token(self):
        claim_token = self.provision().json()['claim_token']
        response = self.register(DEVICE_ID, claim_token)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data['device_token'].startswith(f'{DEVICE_ID}_'))
        self.assertIn('public_camera_id', data)
        camera = Camera.objects.get(device_id=DEVICE_ID)
        self.assertEqual(
            camera.device_token_hash,
            hashlib.sha256(data['device_token'].encode('utf-8')).hexdigest(),
        )

    def test_register_camera_invalid_claim_token_returns_400(self):
        self.provision()
        response = self.register(DEVICE_ID, 'x' * 32)
        self.assertEqual(response.status_code, 400)
        camera = Camera.objects.get(device_id=DEVICE_ID)
        self.assertEqual(camera.device_token_hash, '')

    def test_register_unknown_device_returns_404(self):
        response = self.register('nonexistent12345', 'x' * 32)
        self.assertEqual(response.status_code, 404)

    def test_register_claim_token_is_single_use(self):
        claim_token = self.provision().json()['claim_token']
        first = self.register(DEVICE_ID, claim_token)
        self.assertEqual(first.status_code, 201)
        second = self.register(DEVICE_ID, claim_token)
        self.assertEqual(second.status_code, 400)

    def test_register_already_registered_camera_returns_400(self):
        claim_token = self.provision().json()['claim_token']
        first = self.register(DEVICE_ID, claim_token)
        self.assertEqual(first.status_code, 201)
        original_device_token_hash = Camera.objects.get(device_id=DEVICE_ID).device_token_hash

        second = self.register(DEVICE_ID, claim_token)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.json()['detail'], 'Camera already registered')

        camera = Camera.objects.get(device_id=DEVICE_ID)
        self.assertEqual(camera.device_token_hash, original_device_token_hash)

    def test_register_already_registered_camera_rejects_even_with_wrong_claim_token(self):
        claim_token = self.provision().json()['claim_token']
        self.register(DEVICE_ID, claim_token)

        response = self.register(DEVICE_ID, 'x' * 32)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'Camera already registered')

    # --- Claim ---

    def test_claim_camera_requires_authentication_returns_401(self):
        response = self.claim('irrelevant_token')
        self.assertEqual(response.status_code, 401)

    def test_claim_camera_returns_200_and_sets_owner(self):
        claim_token = self.provision().json()['claim_token']

        self.authenticate(self.user)
        response = self.claim(claim_token, location='Back yard')
        self.assertEqual(response.status_code, 200)

        camera = Camera.objects.get(device_id=DEVICE_ID)
        self.assertEqual(camera.owner, self.user)
        self.assertTrue(camera.claimed)
        self.assertIsNotNone(camera.claimed_at)
        self.assertEqual(camera.location, 'Back yard')

    def test_claim_camera_with_invalid_token_returns_400_and_does_not_claim(self):
        claim_token = self.provision().json()['claim_token']
        self.register(DEVICE_ID, claim_token)

        self.authenticate(self.user)
        # Correct device_id prefix, but a forged/incorrect secret.
        forged_token = f'{DEVICE_ID}_not-the-real-secret'
        response = self.claim(forged_token)
        self.assertEqual(response.status_code, 400)

        camera = Camera.objects.get(device_id=DEVICE_ID)
        self.assertIsNone(camera.owner)
        self.assertFalse(camera.claimed)

    def test_claim_unknown_device_returns_404(self):
        self.authenticate(self.user)
        response = self.claim('nonexistent12345_somesecret')
        self.assertEqual(response.status_code, 404)

    def test_claim_already_claimed_camera_returns_400(self):
        claim_token = self.provision().json()['claim_token']
        self.register(DEVICE_ID, claim_token)

        self.authenticate(self.user)
        self.claim(claim_token)

        other_user = User.objects.create_user(
            username='bob', email='bob@example.com', password='StrongPass123!',
            first_name='Bob', last_name='Jones',
        )
        self.authenticate(other_user)
        response = self.claim(claim_token)
        self.assertEqual(response.status_code, 400)
        camera = Camera.objects.get(device_id=DEVICE_ID)
        self.assertEqual(camera.owner, self.user)

    def test_claim_camera_clears_claim_token_hash(self):
        claim_token = self.provision().json()['claim_token']

        self.authenticate(self.user)
        self.claim(claim_token)

        camera = Camera.objects.get(device_id=DEVICE_ID)
        self.assertEqual(camera.claim_token_hash, '')

    def test_claim_camera_works_without_prior_registration(self):
        claim_token = self.provision().json()['claim_token']

        self.authenticate(self.user)
        response = self.claim(claim_token, location='Back yard')
        self.assertEqual(response.status_code, 200)

        camera = Camera.objects.get(device_id=DEVICE_ID)
        self.assertEqual(camera.owner, self.user)
        self.assertTrue(camera.claimed)


class PresignedUploadTests(TestCase):
    """PresignedImageUploadUrlView is called by the camera itself, authenticated with a
    camera-scoped JWT (see CameraTokenExchangeTests), not a human user's JWT. The
    target camera is derived from the token, not from a URL/body parameter."""

    def setUp(self):
        # get_s3_client() is process-cached via lru_cache, so a client (real or
        # mocked) created by an earlier test would otherwise leak into this one.
        get_s3_client.cache_clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='StrongPass123!',
            first_name='Alice', last_name='Smith',
        )
        self.camera = Camera.objects.create(owner=self.user, location='Front door')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {camera_access_token(self.camera)}')

    def presign(self, content_type='image/jpeg', upload_type='DETECTION'):
        url = reverse('camera:presigned_upload')
        if upload_type is not None:
            url = f'{url}?upload_type={upload_type}'
        return self.client.post(url, data={'content_type': content_type}, format='json')

    @patch('camera.s3_client.boto3.client')
    def test_presigned_upload_detection_returns_url_for_authenticated_camera(self, mock_boto_client):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = 'https://example.com/presigned'
        mock_boto_client.return_value = mock_s3

        response = self.presign(upload_type='DETECTION')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['url'], 'https://example.com/presigned')
        self.assertTrue(data['key'].startswith(f'detection/{self.camera.public_camera_id}/'))
        self.assertTrue(data['key'].endswith('.jpeg'))
        self.assertEqual(data['expires_in'], 300)

        _, kwargs = mock_s3.generate_presigned_url.call_args
        self.assertEqual(kwargs['Params']['ContentType'], 'image/jpeg')

    @patch('camera.s3_client.boto3.client')
    def test_presigned_upload_detection_uses_authenticated_camera_even_if_another_camera_exists(self, mock_boto_client):
        Camera.objects.create(owner=self.user, location='Garage')
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = 'https://example.com/presigned'
        mock_boto_client.return_value = mock_s3

        response = self.presign(upload_type='DETECTION')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['key'].startswith(f'detection/{self.camera.public_camera_id}/'))

    @patch('camera.s3_client.boto3.client')
    def test_presigned_upload_camera_preview_returns_fixed_latest_key(self, mock_boto_client):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = 'https://example.com/presigned'
        mock_boto_client.return_value = mock_s3

        response = self.presign(upload_type='CAMERA_PREVIEW')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['key'],
            f'preview/{self.camera.public_camera_id}/latest.jpg',
        )

    @patch('camera.s3_client.boto3.client')
    def test_presigned_upload_camera_preview_key_is_always_jpg_regardless_of_content_type(self, mock_boto_client):
        """The download side always requests latest.jpg, so the upload key must match
        even when the device uploads a PNG preview."""
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = 'https://example.com/presigned'
        mock_boto_client.return_value = mock_s3

        response = self.presign(content_type='image/png', upload_type='CAMERA_PREVIEW')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['key'],
            f'preview/{self.camera.public_camera_id}/latest.jpg',
        )

    def test_presigned_upload_missing_upload_type_returns_400(self):
        response = self.presign(upload_type=None)
        self.assertEqual(response.status_code, 400)

    def test_presigned_upload_invalid_upload_type_returns_400(self):
        response = self.presign(upload_type='NOT_A_REAL_TYPE')
        self.assertEqual(response.status_code, 400)

    def test_presigned_upload_rejects_unsupported_content_type(self):
        response = self.presign(content_type='text/plain', upload_type='DETECTION')
        self.assertEqual(response.status_code, 400)

    def test_presigned_upload_requires_authentication_returns_401(self):
        self.client.credentials()
        response = self.presign()
        self.assertEqual(response.status_code, 401)

    def test_presigned_upload_rejects_a_human_users_jwt(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        response = self.presign()
        self.assertEqual(response.status_code, 401)

    def test_presigned_upload_rejects_jwt_of_revoked_camera(self):
        self.camera.revoked = True
        self.camera.save()
        response = self.presign()
        self.assertEqual(response.status_code, 401)

    def test_presigned_upload_rejects_jwt_of_deleted_camera(self):
        self.camera.delete()
        response = self.presign()
        self.assertEqual(response.status_code, 401)


class CameraPreviewTimeTests(TestCase):
    """Covers CameraPreviewTimeView, which lets an authenticated camera record that
    it just refreshed its preview image."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='StrongPass123!',
            first_name='Alice', last_name='Smith',
        )
        self.camera = Camera.objects.create(owner=self.user, location='Front door')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {camera_access_token(self.camera)}')

    def update_preview_time(self):
        return self.client.post(reverse('camera:update_preview_time'))

    def test_update_preview_time_returns_200_and_sets_timestamp(self):
        self.assertIsNone(self.camera.preview_updated_at)
        response = self.update_preview_time()
        self.assertEqual(response.status_code, 200)
        self.camera.refresh_from_db()
        self.assertIsNotNone(self.camera.preview_updated_at)

    def test_update_preview_time_requires_authentication_returns_401(self):
        self.client.credentials()
        response = self.update_preview_time()
        self.assertEqual(response.status_code, 401)

    def test_update_preview_time_rejects_a_human_users_jwt(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        response = self.update_preview_time()
        self.assertEqual(response.status_code, 401)

    def test_update_preview_time_rejects_jwt_of_revoked_camera(self):
        self.camera.revoked = True
        self.camera.save()
        response = self.update_preview_time()
        self.assertEqual(response.status_code, 401)


class CameraTokenExchangeTests(TestCase):
    """Covers exchanging a device token (from CameraRegistrationView) for a
    short-lived camera-scoped JWT via CameraTokenExchangeView."""

    def setUp(self):
        self.client = APIClient()
        claim_token = self.client.post(
            reverse('camera:create_camera'), data={'device_id': DEVICE_ID}, format='json'
        ).json()['claim_token']
        self.device_token = self.client.post(
            reverse('camera:register_camera'),
            data={'device_id': DEVICE_ID, 'claim_token': claim_token},
            format='json',
        ).json()['device_token']
        self.camera = Camera.objects.get(device_id=DEVICE_ID)

    def exchange(self, device_token=None, header=None):
        kwargs = {}
        if header is not None:
            kwargs['HTTP_AUTHORIZATION'] = header
        elif device_token is not None:
            kwargs['HTTP_AUTHORIZATION'] = f'Device {device_token}'
        return self.client.post(reverse('camera:token_exchange'), **kwargs)

    def test_token_exchange_returns_camera_scoped_jwt(self):
        response = self.exchange(self.device_token)
        self.assertEqual(response.status_code, 200)
        token = AccessToken(response.json()['access'])
        self.assertEqual(token['scope'], 'camera')
        self.assertEqual(token['public_camera_id'], str(self.camera.public_camera_id))

    def test_token_exchange_invalid_device_token_returns_401(self):
        response = self.exchange('not-a-real-token')
        self.assertEqual(response.status_code, 401)

    def test_token_exchange_missing_auth_header_returns_401(self):
        response = self.exchange()
        self.assertEqual(response.status_code, 401)

    def test_token_exchange_malformed_header_returns_401(self):
        response = self.exchange(header='Device')
        self.assertEqual(response.status_code, 401)

    def test_token_exchange_revoked_camera_returns_401(self):
        self.camera.revoked = True
        self.camera.save()
        response = self.exchange(self.device_token)
        self.assertEqual(response.status_code, 401)

    def test_camera_jwt_cannot_authenticate_as_a_user(self):
        access = self.exchange(self.device_token).json()['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        response = self.client.get(reverse('camera:camera-list'))
        self.assertEqual(response.status_code, 401)
