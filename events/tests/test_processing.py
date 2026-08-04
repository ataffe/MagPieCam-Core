from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from camera.models import Camera
from events import processing
from events.processing import create_notifications, process_camera_image
from notifications.models import Notification
from rules.models import Rule
from users.models import User


class CreateNotificationsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com',
            password='StrongPass123!', first_name='Alice', last_name='Smith')
        self.camera = Camera.objects.create(owner=self.user, location='Front Door')
        self.rule = Rule.objects.create(
            owner=self.user, camera=self.camera,
            rule='a person is present', rule_nickname='Person Detection')
        self.camera_id = str(self.camera.public_camera_id)

    def test_creates_one_notification_per_triggered_rule(self):
        other_rule = Rule.objects.create(
            owner=self.user, camera=self.camera,
            rule='a dog is present', rule_nickname='Dog Detection')

        created = create_notifications(
            self.camera_id,
            [str(self.rule.public_rule_id), str(other_rule.public_rule_id)])

        self.assertEqual(len(created), 2)
        self.assertEqual(Notification.objects.filter(camera=self.camera).count(), 2)

    def test_notification_links_camera_and_rule(self):
        create_notifications(self.camera_id, [str(self.rule.public_rule_id)])

        notification = Notification.objects.get()
        self.assertEqual(notification.camera, self.camera)
        self.assertEqual(notification.rule, self.rule)

    def test_no_triggered_rules_creates_nothing(self):
        self.assertEqual(create_notifications(self.camera_id, []), [])
        self.assertEqual(Notification.objects.count(), 0)

    def test_unknown_camera_creates_nothing(self):
        created = create_notifications(str(uuid4()), [str(self.rule.public_rule_id)])

        self.assertEqual(created, [])
        self.assertEqual(Notification.objects.count(), 0)

    def test_rule_belonging_to_another_camera_is_ignored(self):
        """A model that echoes back an id it was never given must not be able
        to create a notification against an unrelated camera."""
        other_camera = Camera.objects.create(owner=self.user, location='Garage')
        foreign_rule = Rule.objects.create(
            owner=self.user, camera=other_camera,
            rule='a cat is present', rule_nickname='Cat Detection')

        created = create_notifications(
            self.camera_id, [str(foreign_rule.public_rule_id)])

        self.assertEqual(created, [])
        self.assertEqual(Notification.objects.count(), 0)

    def test_unknown_rule_id_is_ignored(self):
        created = create_notifications(self.camera_id, [str(uuid4())])

        self.assertEqual(created, [])
        self.assertEqual(Notification.objects.count(), 0)


class ProcessCameraImageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com',
            password='StrongPass123!', first_name='Alice', last_name='Smith')
        self.camera = Camera.objects.create(owner=self.user, location='Front Door')
        self.rule = Rule.objects.create(
            owner=self.user, camera=self.camera,
            rule='a person is present', rule_nickname='Person Detection')
        self.camera_id = str(self.camera.public_camera_id)
        # The model is a per-process singleton; don't leak one test's stub.
        processing.get_rules_model.cache_clear()
        self.addCleanup(processing.get_rules_model.cache_clear)

    def test_triggered_rule_creates_notification(self):
        with patch.object(processing, 'get_rules_model') as get_model:
            get_model.return_value.evaluate_rules.return_value = [
                str(self.rule.public_rule_id)]

            notifications = process_camera_image(self.camera_id, image=object())

        self.assertEqual(len(notifications), 1)
        self.assertEqual(Notification.objects.get().rule, self.rule)

    def test_no_triggered_rules_creates_no_notification(self):
        with patch.object(processing, 'get_rules_model') as get_model:
            get_model.return_value.evaluate_rules.return_value = []

            notifications = process_camera_image(self.camera_id, image=object())

        self.assertEqual(notifications, [])
        self.assertEqual(Notification.objects.count(), 0)

    def test_camera_with_no_enabled_rules_skips_the_model_entirely(self):
        """Loading the rules model is expensive; a camera with nothing to
        evaluate must not pay for it."""
        self.rule.is_enabled = False
        self.rule.save()

        with patch.object(processing, 'get_rules_model') as get_model:
            notifications = process_camera_image(self.camera_id, image=object())

        get_model.assert_not_called()
        self.assertEqual(notifications, [])

    def test_unknown_camera_creates_no_notification(self):
        with patch.object(processing, 'get_rules_model') as get_model:
            notifications = process_camera_image(str(uuid4()), image=object())

        get_model.assert_not_called()
        self.assertEqual(notifications, [])

    def test_image_and_rules_are_passed_to_the_model(self):
        image = object()
        with patch.object(processing, 'get_rules_model') as get_model:
            get_model.return_value.evaluate_rules.return_value = []

            process_camera_image(self.camera_id, image)

        request = get_model.return_value.evaluate_rules.call_args.args[0]
        self.assertIs(request.image, image)
        self.assertEqual(
            [r.public_rule_id for r in request.rules],
            [str(self.rule.public_rule_id)])
