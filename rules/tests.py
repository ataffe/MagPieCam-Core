from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

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

class RuleTests(TestCase):
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

    def get_jwt_token(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)

    def authenticate(self, user):
        token = self.get_jwt_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _rules_list_url(self, camera=None):
        camera = camera or self.camera
        return reverse('rules:camera-rules-list', kwargs={
            'camera_public_camera_id': camera.public_camera_id,
        })

    def _rule_detail_url(self, rule=None, camera=None):
        rule = rule or self.rule
        camera = camera or self.camera
        return reverse('rules:camera-rules-detail', kwargs={
            'camera_public_camera_id': camera.public_camera_id,
            'public_rule_id': rule.public_rule_id,
        })

    def test_list_rules_returns_only_camera_rules(self):
        other_camera = Camera.objects.create(owner=self.user, location='Garage')
        Rule.objects.create(owner=self.user, camera=other_camera, rule='Other rule', rule_nickname='Other')
        response = self.client.get(self._rules_list_url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['rule'], 'Notify on motion')

    def test_list_returns_empty_when_no_rules(self):
        Rule.objects.filter(camera=self.camera).delete()
        response = self.client.get(self._rules_list_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_create_rule_returns_201_and_persists(self):
        payload = {'rule': 'Notify on sound', 'rule_nickname': 'Sound alert'}
        response = self.client.post(self._rules_list_url(), data=payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Rule.objects.filter(rule='Notify on sound', camera=self.camera).exists())

    def test_create_rule_missing_required_fields_returns_400(self):
        response = self.client.post(
            self._rules_list_url(),
            data={'rule': 'Notify on sound'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_create_response_includes_public_rule_id(self):
        payload = {'rule': 'Notify on sound', 'rule_nickname': 'Sound alert'}
        response = self.client.post(self._rules_list_url(), data=payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('public_rule_id', response.json())

    def test_create_rule_is_enabled_by_default(self):
        payload = {'rule': 'Notify on sound', 'rule_nickname': 'Sound alert'}
        response = self.client.post(self._rules_list_url(), data=payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['is_enabled'])

    def test_get_rule_returns_correct_data(self):
        response = self.client.get(self._rule_detail_url())
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['rule'], 'Notify on motion')
        self.assertEqual(data['rule_nickname'], 'Motion alert')

    def test_update_rule_nickname(self):
        response = self.client.patch(
            self._rule_detail_url(),
            data={'rule_nickname': 'Updated alert'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.rule_nickname, 'Updated alert')

    def test_toggle_is_enabled(self):
        response = self.client.patch(
            self._rule_detail_url(),
            data={'is_enabled': False},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.rule.refresh_from_db()
        self.assertFalse(self.rule.is_enabled)

    def test_delete_rule_returns_204_and_removes_record(self):
        response = self.client.delete(self._rule_detail_url())
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Rule.objects.filter(pk=self.rule.pk).exists())

    def test_access_rules_on_other_users_camera_returns_403(self):
        other_camera = Camera.objects.create(owner=self.other_user, location='Garage')
        response = self.client.get(self._rules_list_url(camera=other_camera))
        self.assertEqual(response.status_code, 403)

    def test_update_rule_on_other_users_camera_returns_403(self):
        other_camera = Camera.objects.create(owner=self.other_user, location='Garage')
        other_rule = Rule.objects.create(
            owner=self.other_user, camera=other_camera,
            rule='Other rule', rule_nickname='Other',
        )
        response = self.client.patch(
            self._rule_detail_url(rule=other_rule, camera=other_camera),
            data={'rule_nickname': 'Hacked'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        other_rule.refresh_from_db()
        self.assertEqual(other_rule.rule_nickname, 'Other')

    def test_delete_rule_on_other_users_camera_returns_403(self):
        other_camera = Camera.objects.create(owner=self.other_user, location='Garage')
        other_rule = Rule.objects.create(
            owner=self.other_user, camera=other_camera,
            rule='Other rule', rule_nickname='Other',
        )
        response = self.client.delete(
            self._rule_detail_url(rule=other_rule, camera=other_camera)
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Rule.objects.filter(pk=other_rule.pk).exists())

    def test_rule_exceeds_max_length_returns_400(self):
        payload = {'rule': 'A' * 241, 'rule_nickname': 'Too long'}
        response = self.client.post(self._rules_list_url(), data=payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_access_returns_401(self):
        self.client.credentials()
        response = self.client.get(self._rules_list_url())
        self.assertEqual(response.status_code, 401)
