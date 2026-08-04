import uuid

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

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
        self.notification = Notification.objects.create(camera=self.camera, rule=self.rule)

    def get_jwt_token(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)

    def authenticate(self, user):
        token = self.get_jwt_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _notifications_list_url(self, camera=None):
        camera = camera or self.camera
        return reverse('notifications:camera-notifications-list', kwargs={
            'public_camera_id_public_camera_id': camera.public_camera_id,
        })

    def _notification_detail_url(self, public_notification_id=None, camera=None):
        public_notification_id = public_notification_id or self.notification.public_notification_id
        camera = camera or self.camera
        return reverse('notifications:camera-notifications-detail', kwargs={
            'public_camera_id_public_camera_id': camera.public_camera_id,
            'public_notification_id': public_notification_id,
        })

    def test_list_notifications_returns_only_camera_notifications(self):
        other_camera = Camera.objects.create(owner=self.user, location='Garage')
        other_rule = Rule.objects.create(
            owner=self.user, camera=other_camera,
            rule='Other rule', rule_nickname='Other',
        )
        Notification.objects.create(camera=other_camera, rule=other_rule)

        response = self.client.get(self._notifications_list_url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['public_notification_id'], str(self.notification.public_notification_id))

    def test_list_returns_empty_when_no_notifications(self):
        Notification.objects.filter(camera=self.camera).delete()
        response = self.client.get(self._notifications_list_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_list_ordered_newest_first(self):
        second = Notification.objects.create(camera=self.camera, rule=self.rule)
        response = self.client.get(self._notifications_list_url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data[0]['public_notification_id'], str(second.public_notification_id))
        self.assertEqual(data[1]['public_notification_id'], str(self.notification.public_notification_id))

    def test_retrieve_notification_returns_correct_data(self):
        response = self.client.get(self._notification_detail_url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['public_notification_id'], str(self.notification.public_notification_id))
        self.assertEqual(data['rule'], self.rule.id)

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
        other_notification = Notification.objects.create(camera=other_camera, rule=other_rule)
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

    def test_deleting_camera_cascades_to_notifications(self):
        self.camera.delete()
        self.assertFalse(Notification.objects.filter(pk=self.notification.pk).exists())
