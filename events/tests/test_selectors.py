"""Ported from the standalone service's tests/test_db_rules.py.

Same behaviour, on the Django ORM instead of SQLAlchemy against in-memory
sqlite -- plus coverage for the is_enabled filtering the old query was missing.
"""
from uuid import uuid4

from django.test import TestCase

from camera.models import Camera
from events.selectors import get_rule_dtos_by_camera_ids
from rules.models import Rule
from users.models import User


class GetRuleDtosByCameraIdsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com',
            password='StrongPass123!', first_name='Alice', last_name='Smith',
        )
        self.camera1 = Camera.objects.create(owner=self.user, location='Front Door')
        self.camera2 = Camera.objects.create(owner=self.user, location='Back Door')

        self.person_rule = Rule.objects.create(
            owner=self.user, camera=self.camera1,
            rule='a person is present', rule_nickname='Person Detection')
        self.vehicle_rule = Rule.objects.create(
            owner=self.user, camera=self.camera1,
            rule='a vehicle is present', rule_nickname='Vehicle Detection')
        self.dog_rule = Rule.objects.create(
            owner=self.user, camera=self.camera2,
            rule='a dog is present', rule_nickname='Dog Detection')

        self.camera1_id = str(self.camera1.public_camera_id)
        self.camera2_id = str(self.camera2.public_camera_id)

    def test_returns_all_rules_for_matching_camera(self):
        rules_by_camera = get_rule_dtos_by_camera_ids([self.camera1_id])
        self.assertEqual(len(rules_by_camera[self.camera1_id]), 2)

    def test_does_not_return_other_cameras_rules(self):
        rules_by_camera = get_rule_dtos_by_camera_ids([self.camera1_id])
        rule_texts = {r.rule_text for r in rules_by_camera[self.camera1_id]}
        self.assertNotIn('a dog is present', rule_texts)

    def test_returns_correct_rule_content(self):
        rules_by_camera = get_rule_dtos_by_camera_ids([self.camera1_id])
        rule_texts = {r.rule_text for r in rules_by_camera[self.camera1_id]}
        self.assertEqual(rule_texts, {'a person is present', 'a vehicle is present'})

    def test_maps_nickname_to_rule_name(self):
        rules_by_camera = get_rule_dtos_by_camera_ids([self.camera2_id])
        self.assertEqual(rules_by_camera[self.camera2_id][0].rule_name, 'Dog Detection')

    def test_returns_single_rule_for_second_camera(self):
        rules_by_camera = get_rule_dtos_by_camera_ids([self.camera2_id])
        rules = rules_by_camera[self.camera2_id]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_text, 'a dog is present')

    def test_returns_empty_list_for_unknown_camera_id(self):
        unknown_id = str(uuid4())
        rules_by_camera = get_rule_dtos_by_camera_ids([unknown_id])
        self.assertEqual(rules_by_camera[unknown_id], [])

    def test_returns_empty_list_when_camera_has_no_rules(self):
        bare_camera = Camera.objects.create(owner=self.user, location='Garage')
        bare_id = str(bare_camera.public_camera_id)
        rules_by_camera = get_rule_dtos_by_camera_ids([bare_id])
        self.assertEqual(rules_by_camera[bare_id], [])

    def test_groups_rules_by_camera(self):
        rules_by_camera = get_rule_dtos_by_camera_ids(
            [self.camera1_id, self.camera2_id])

        self.assertEqual(len(rules_by_camera), 2)
        self.assertEqual(
            {r.rule_text for r in rules_by_camera[self.camera1_id]},
            {'a person is present', 'a vehicle is present'})
        self.assertEqual(
            {r.rule_text for r in rules_by_camera[self.camera2_id]},
            {'a dog is present'})

    def test_only_returns_requested_cameras(self):
        rules_by_camera = get_rule_dtos_by_camera_ids([self.camera1_id])
        self.assertEqual(list(rules_by_camera.keys()), [self.camera1_id])
        self.assertEqual(len(rules_by_camera[self.camera1_id]), 2)

    def test_includes_empty_list_for_camera_without_rules(self):
        unknown_id = str(uuid4())
        rules_by_camera = get_rule_dtos_by_camera_ids([self.camera2_id, unknown_id])
        self.assertNotEqual(rules_by_camera[self.camera2_id], [])
        self.assertEqual(rules_by_camera[unknown_id], [])

    def test_returns_empty_dict_for_empty_input(self):
        self.assertEqual(get_rule_dtos_by_camera_ids([]), {})

    def test_disabled_rules_are_excluded(self):
        """The SQLAlchemy query never filtered is_enabled, so a rule the user
        switched off still got evaluated and could fire a notification."""
        self.vehicle_rule.is_enabled = False
        self.vehicle_rule.save()

        rules_by_camera = get_rule_dtos_by_camera_ids([self.camera1_id])

        rule_texts = {r.rule_text for r in rules_by_camera[self.camera1_id]}
        self.assertEqual(rule_texts, {'a person is present'})

    def test_camera_with_only_disabled_rules_returns_empty_list(self):
        self.dog_rule.is_enabled = False
        self.dog_rule.save()

        rules_by_camera = get_rule_dtos_by_camera_ids([self.camera2_id])

        self.assertEqual(rules_by_camera[self.camera2_id], [])
