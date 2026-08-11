import uuid
from unittest.mock import patch, MagicMock, mock_open

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from notifications import apns_client
from notifications.models import Notification
from rules.models import Rule
from users.models import User
from camera.models import Camera


def make_user(username, email, password='StrongPass123!', first_name='Test', last_name='User'):
    return User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )


class NotificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user('alice', 'alice@example.com', first_name='Alice', last_name='Smith')
        self.other_user = make_user('bob', 'bob@example.com', first_name='Bob', last_name='Jones')
        self.authenticate(self.user)
        self.camera = Camera.objects.create(owner=self.user, location='Front door')
        self.rule = Rule.objects.create(
            owner=self.user,
            camera=self.camera,
            rule='Notify on motion',
            rule_nickname='Motion alert',
        )
        self.notification = Notification.objects.create(
            camera=self.camera, rule=self.rule, rule_nickname=self.rule.rule_nickname)

    def get_jwt_token(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)

    def authenticate(self, user):
        token = self.get_jwt_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _notifications_list_url(self, camera=None):
        camera = camera or self.camera
        return reverse('notifications:camera-notifications-list', kwargs={
            'camera_public_camera_id': camera.public_camera_id,
        })

    def _notification_detail_url(self, public_notification_id=None, camera=None):
        public_notification_id = public_notification_id or self.notification.public_notification_id
        camera = camera or self.camera
        return reverse('notifications:camera-notifications-detail', kwargs={
            'camera_public_camera_id': camera.public_camera_id,
            'public_notification_id': public_notification_id,
        })

    def test_list_notifications_returns_only_camera_notifications(self):
        other_camera = Camera.objects.create(owner=self.user, location='Garage')
        other_rule = Rule.objects.create(
            owner=self.user, camera=other_camera,
            rule='Other rule', rule_nickname='Other',
        )
        Notification.objects.create(
            camera=other_camera, rule=other_rule, rule_nickname=other_rule.rule_nickname)

        response = self.client.get(self._notifications_list_url())
        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['public_notification_id'], str(self.notification.public_notification_id))

    def test_list_returns_empty_when_no_notifications(self):
        Notification.objects.filter(camera=self.camera).delete()
        response = self.client.get(self._notifications_list_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])

    def test_list_ordered_newest_first(self):
        second = Notification.objects.create(
            camera=self.camera, rule=self.rule, rule_nickname=self.rule.rule_nickname)
        response = self.client.get(self._notifications_list_url())
        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        self.assertEqual(results[0]['public_notification_id'], str(second.public_notification_id))
        self.assertEqual(results[1]['public_notification_id'], str(self.notification.public_notification_id))

    def test_list_next_cursor_is_a_bare_token_not_a_url(self):
        for _ in range(3):
            Notification.objects.create(
                camera=self.camera, rule=self.rule, rule_nickname=self.rule.rule_nickname)

        # NotificationPagination has no page_size query param wired up, so
        # shrink the page by patching the pagination class directly instead.
        from notifications.views import NotificationPagination
        original_page_size = NotificationPagination.page_size
        NotificationPagination.page_size = 2
        try:
            response = self.client.get(self._notifications_list_url())
        finally:
            NotificationPagination.page_size = original_page_size

        self.assertEqual(response.status_code, 200)
        next_cursor = response.json()['next']
        self.assertIsNotNone(next_cursor)
        self.assertNotIn('://', next_cursor)
        self.assertNotIn('/', next_cursor)
        self.assertNotIn(self._notifications_list_url(), next_cursor)

    def test_list_next_cursor_round_trips_to_the_following_page(self):
        notifications = [self.notification]
        for _ in range(3):
            notifications.append(Notification.objects.create(
                camera=self.camera, rule=self.rule, rule_nickname=self.rule.rule_nickname))
        # Newest first: notifications[3] is first page, notifications[0] is last.

        from notifications.views import NotificationPagination
        original_page_size = NotificationPagination.page_size
        NotificationPagination.page_size = 2
        try:
            first_page = self.client.get(self._notifications_list_url())
            next_cursor = first_page.json()['next']
            second_page = self.client.get(self._notifications_list_url(), {'cursor': next_cursor})
        finally:
            NotificationPagination.page_size = original_page_size

        self.assertEqual(second_page.status_code, 200)
        second_page_ids = [n['public_notification_id'] for n in second_page.json()['results']]
        self.assertEqual(second_page_ids, [
            str(notifications[1].public_notification_id),
            str(notifications[0].public_notification_id),
        ])

    def test_retrieve_notification_returns_correct_data(self):
        response = self.client.get(self._notification_detail_url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['public_notification_id'], str(self.notification.public_notification_id))
        self.assertEqual(data['rule_nickname'], self.rule.rule_nickname)
        self.assertEqual(data['public_camera_id'], str(self.camera.public_camera_id))

    def test_retrieve_notification_not_found(self):
        response = self.client.get(self._notification_detail_url(public_notification_id=uuid.uuid4()))
        self.assertEqual(response.status_code, 404)

    def test_access_notifications_on_other_users_camera_returns_404(self):
        other_camera = Camera.objects.create(owner=self.other_user, location='Garage')
        response = self.client.get(self._notifications_list_url(camera=other_camera))
        self.assertEqual(response.status_code, 404)

    def test_retrieve_notification_on_other_users_camera_returns_404(self):
        other_camera = Camera.objects.create(owner=self.other_user, location='Garage')
        other_rule = Rule.objects.create(
            owner=self.other_user, camera=other_camera,
            rule='Other rule', rule_nickname='Other',
        )
        other_notification = Notification.objects.create(
            camera=other_camera, rule=other_rule, rule_nickname=other_rule.rule_nickname)
        response = self.client.get(self._notification_detail_url(
            public_notification_id=other_notification.public_notification_id, camera=other_camera,
        ))
        self.assertEqual(response.status_code, 404)

    def test_create_notification_not_allowed(self):
        response = self.client.post(
            self._notifications_list_url(),
            data={'camera': self.camera.id, 'rule': self.rule.id},
            format='json',
        )
        self.assertEqual(response.status_code, 405)

    def test_delete_notification_not_allowed(self):
        response = self.client.delete(self._notification_detail_url())
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Notification.objects.filter(pk=self.notification.pk).exists())

    def test_unauthenticated_access_returns_401(self):
        self.client.credentials()
        response = self.client.get(self._notifications_list_url())
        self.assertEqual(response.status_code, 401)

    def test_deleting_rule_sets_notification_rule_to_null(self):
        self.rule.delete()
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.rule)

    def test_retrieve_notification_keeps_rule_nickname_after_rule_deleted(self):
        # rule_nickname is copied onto the notification at creation time
        # specifically so it survives rule deletion -- SET_NULL only clears the
        # FK, it doesn't touch this denormalized column.
        expected_nickname = self.rule.rule_nickname
        self.rule.delete()
        response = self.client.get(self._notification_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['rule_nickname'], expected_nickname)

    def test_deleting_camera_cascades_to_notifications(self):
        self.camera.delete()
        self.assertFalse(Notification.objects.filter(pk=self.notification.pk).exists())


PREVIEW_IMG_URL = 'https://s3.example.com/bucket/detection.jpg?X-Amz-Signature=abc'


class ApnsClientTests(TestCase):
    def setUp(self):
        apns_client.cache_storage.clear()
        self.user = make_user('carol', 'carol@example.com', first_name='Carol', last_name='Lee')
        self.user.apns_device_id = 'device-token-abc'
        self.user.save()
        self.camera = Camera.objects.create(owner=self.user, location='Backyard')
        self.rule = Rule.objects.create(
            owner=self.user, camera=self.camera,
            rule='Notify on motion', rule_nickname='Motion alert',
        )
        self.notification = Notification.objects.create(
            camera=self.camera, rule=self.rule, rule_nickname=self.rule.rule_nickname)
        self.addCleanup(apns_client.cache_storage.clear)

    def _mock_client(self, mock_client_cls, status_code=200, json_data=None, content=b'{}', headers=None):
        response = MagicMock()
        response.status_code = status_code
        response.content = content
        response.json.return_value = json_data or {}
        response.headers = headers or {}
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.post.return_value = response
        return instance

    # -- refresh_jwt --

    @patch('notifications.apns_client.jwt.encode', return_value='header.payload.signature')
    @patch('builtins.open', mock_open(read_data=b'FAKE-PRIVATE-KEY'))
    def test_refresh_jwt_returns_raw_token_string(self, mock_encode):
        # Regression test: refresh_jwt used to base64-encode the already-encoded
        # JWT and return bytes, which rendered as "b'...'" garbage once embedded
        # in the Authorization header f-string.
        token = apns_client.refresh_jwt()
        self.assertEqual(token, 'header.payload.signature')
        self.assertIsInstance(token, str)

    @patch('notifications.apns_client.jwt.encode', return_value='header.payload.signature')
    @patch('builtins.open', mock_open(read_data=b'FAKE-PRIVATE-KEY'))
    def test_refresh_jwt_is_cached_within_ttl(self, mock_encode):
        apns_client.refresh_jwt()
        apns_client.refresh_jwt()
        self.assertEqual(mock_encode.call_count, 1)

    @patch('builtins.open', mock_open(read_data=b''))
    def test_refresh_jwt_raises_when_private_key_missing(self, *_):
        with self.assertRaises(FileNotFoundError):
            apns_client.refresh_jwt()

    # -- send_notification --

    @patch('notifications.apns_client.httpx.Client')
    @patch('notifications.apns_client.refresh_jwt', return_value='fake-jwt')
    def test_send_notification_success(self, mock_refresh, mock_client_cls):
        instance = self._mock_client(mock_client_cls, status_code=200)
        result = apns_client.send_notification(self.notification, PREVIEW_IMG_URL)
        self.assertTrue(result)
        called_headers = instance.post.call_args.kwargs['headers']
        self.assertEqual(called_headers['authorization'], 'bearer fake-jwt')
        # apns-priority is cast to int in settings; httpx requires str/bytes header values.
        self.assertIsInstance(called_headers['apns-priority'], str)
        called_url = instance.post.call_args.args[0]
        self.assertEqual(called_url, f'{settings.APNS_URL}/3/device/{self.user.apns_device_id}')

    @patch('notifications.apns_client.httpx.Client')
    @patch('notifications.apns_client.refresh_jwt', return_value='fake-jwt')
    def test_send_notification_includes_preview_image_url_in_payload(
            self, mock_refresh, mock_client_cls):
        instance = self._mock_client(mock_client_cls, status_code=200)
        apns_client.send_notification(self.notification, PREVIEW_IMG_URL)
        called_body = instance.post.call_args.kwargs['json']
        self.assertEqual(called_body['detection-image-url'], PREVIEW_IMG_URL)

    @patch('notifications.apns_client.httpx.Client')
    @patch('notifications.apns_client.refresh_jwt', return_value='fake-jwt')
    def test_send_notification_sets_mutable_content_for_the_image_attachment(
            self, mock_refresh, mock_client_cls):
        # mutable-content=1 is what lets the iOS Notification Service Extension
        # intercept the push and download detection-image-url before display.
        instance = self._mock_client(mock_client_cls, status_code=200)
        apns_client.send_notification(self.notification, PREVIEW_IMG_URL)
        called_body = instance.post.call_args.kwargs['json']
        self.assertEqual(called_body['aps']['mutable-content'], 1)

    @patch('notifications.apns_client.httpx.Client')
    @patch('notifications.apns_client.refresh_jwt', return_value='fake-jwt')
    def test_send_notification_does_not_touch_rule_last_triggered(self, mock_refresh, mock_client_cls):
        # Cooldown bookkeeping now lives in events.processing.create_notifications,
        # not in the APNs transport client.
        self._mock_client(mock_client_cls, status_code=200)
        apns_client.send_notification(self.notification, PREVIEW_IMG_URL)
        self.rule.refresh_from_db()
        self.assertIsNone(self.rule.last_triggered)

    @patch('notifications.apns_client.httpx.Client')
    def test_send_notification_without_device_id_returns_false_without_calling_apns(self, mock_client_cls):
        self.user.apns_device_id = None
        self.user.save()
        result = apns_client.send_notification(self.notification, PREVIEW_IMG_URL)
        self.assertFalse(result)
        mock_client_cls.assert_not_called()

    @patch('notifications.apns_client.httpx.Client')
    @patch('notifications.apns_client.refresh_jwt', side_effect=FileNotFoundError('no key'))
    def test_send_notification_returns_false_when_jwt_refresh_fails(self, mock_refresh, mock_client_cls):
        result = apns_client.send_notification(self.notification, PREVIEW_IMG_URL)
        self.assertFalse(result)
        mock_client_cls.assert_not_called()

    @patch('notifications.apns_client.httpx.Client')
    @patch('notifications.apns_client.refresh_jwt', return_value='fake-jwt')
    def test_send_notification_returns_false_on_client_error_without_retry(self, mock_refresh, mock_client_cls):
        instance = self._mock_client(mock_client_cls, status_code=400, json_data={'reason': 'BadDeviceToken'})
        result = apns_client.send_notification(self.notification, PREVIEW_IMG_URL)
        self.assertFalse(result)
        self.assertEqual(instance.post.call_count, 1)

    @patch('time.sleep', return_value=None)
    @patch('notifications.apns_client.httpx.Client')
    @patch('notifications.apns_client.refresh_jwt', return_value='fake-jwt')
    def test_send_notification_retries_on_500_then_succeeds(self, mock_refresh, mock_client_cls, mock_sleep):
        fail_response = MagicMock(status_code=500, content=b'')
        ok_response = MagicMock(status_code=200, content=b'')
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.post.side_effect = [fail_response, ok_response]
        result = apns_client.send_notification(self.notification, PREVIEW_IMG_URL)
        self.assertTrue(result)
        self.assertEqual(instance.post.call_count, 2)

    @patch('time.sleep', return_value=None)
    @patch('notifications.apns_client.httpx.Client')
    @patch('notifications.apns_client.refresh_jwt', return_value='fake-jwt')
    def test_send_notification_gives_up_after_exhausting_retries(self, mock_refresh, mock_client_cls, mock_sleep):
        # Regression test: the 500 -> APNServiceError used to be raised and caught
        # within the same try/except, so it never reached tenacity and no retry
        # ever happened. Confirms retries now actually occur and failure still
        # surfaces as `False` rather than an unhandled exception.
        fail_response = MagicMock(status_code=500, content=b'')
        instance = mock_client_cls.return_value.__enter__.return_value
        instance.post.return_value = fail_response
        result = apns_client.send_notification(self.notification, PREVIEW_IMG_URL)
        self.assertFalse(result)
        self.assertEqual(instance.post.call_count, settings.APNS_CLIENT_RETRIES)
