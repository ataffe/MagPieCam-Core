from unittest.mock import patch

from django.test import TestCase

from camera.media_keys import clip_key, detection_key
from camera.models import Camera
from events import tasks
from events.tasks import attach_video_clip, evaluate_camera_image
from notifications.models import Notification
from rules.models import Rule
from users.models import User


DETECTION_PREVIEW_URL = 'https://s3.example.com/bucket/detection.jpg?X-Amz-Signature=abc'


class EvaluateCameraImageTests(TestCase):
    def setUp(self):
        storage_patcher = patch.object(tasks, 'get_s3_image_storage_client')
        sqs_patcher = patch.object(tasks, 'SQSImageQueueClient')
        processing_patcher = patch.object(tasks, 'process_camera_image')
        send_patcher = patch.object(tasks, 'send_notification')
        self.storage = storage_patcher.start().return_value
        self.sqs_cls = sqs_patcher.start()
        self.process = processing_patcher.start()
        self.send = send_patcher.start()
        self.addCleanup(storage_patcher.stop)
        self.addCleanup(sqs_patcher.stop)
        self.addCleanup(processing_patcher.stop)
        self.addCleanup(send_patcher.stop)

        # Nothing fired unless a test says otherwise.
        self.process.return_value = None
        self.send.return_value = True
        self.storage.get_image_download_url.return_value = DETECTION_PREVIEW_URL

        self.user = User.objects.create_user(
            username='alice', email='alice@example.com',
            password='StrongPass123!', first_name='Alice', last_name='Smith')
        self.camera = Camera.objects.create(owner=self.user, location='Front Door')

    def _triggered_notification(self, *nicknames):
        """Stand in for what process_camera_image would have created: one
        notification bundling every rule that fired on this image."""
        nicknames = nicknames or ('Person Detection',)
        rules = [
            Rule.objects.create(
                owner=self.user, camera=self.camera,
                rule=f'a {nickname} is present', rule_nickname=nickname)
            for nickname in nicknames
        ]
        notification = Notification.objects.create(
            camera=self.camera, rule_nicknames=list(nicknames))
        notification.rules.set(rules)
        self.process.return_value = notification
        return notification

    def test_downloads_the_object_named_in_the_event(self):
        evaluate_camera_image('my-bucket', 'detect/cam-1/img.jpg', 'cam-1')

        self.storage.download_image.assert_called_once_with(
            'my-bucket', 'detect/cam-1/img.jpg')

    def test_passes_downloaded_image_to_processing(self):
        image = self.storage.download_image.return_value

        evaluate_camera_image('my-bucket', 'detect/cam-1/img.jpg', 'cam-1')

        self.process.assert_called_once_with(
            'cam-1', image, detection_image_key='detect/cam-1/img.jpg')

    def test_sends_a_single_push_for_the_bundled_notification(self):
        """Several rules firing on one image is one push, not one per rule."""
        notification = self._triggered_notification('Person Detection', 'Dog Detection')

        evaluate_camera_image('b', 'k', 'cam-1')

        self.send.assert_called_once_with(notification, DETECTION_PREVIEW_URL)

    def test_notification_becomes_visible_once_the_push_is_delivered(self):
        notification = self._triggered_notification()

        evaluate_camera_image('b', 'k', 'cam-1', 'handle-abc')

        notification.refresh_from_db()
        self.assertTrue(notification.visible)
        self.sqs_cls.return_value.delete_message.assert_called_once_with('handle-abc')

    def test_failed_push_drops_the_notification_and_leaves_the_message_queued(self):
        """The app must not surface a notification the user was never pushed;
        keeping the message queued lets the whole thing be retried."""
        self.send.return_value = False
        notification = self._triggered_notification()

        evaluate_camera_image('b', 'k', 'cam-1', 'handle-abc')

        self.assertFalse(Notification.objects.filter(pk=notification.pk).exists())
        self.sqs_cls.return_value.delete_message.assert_not_called()

    def test_no_push_is_sent_when_no_rule_fired(self):
        evaluate_camera_image('b', 'k', 'cam-1', 'handle-abc')

        self.send.assert_not_called()
        # The image was still handled, so the message must not be redelivered.
        self.sqs_cls.return_value.delete_message.assert_called_once_with('handle-abc')

    def test_deletes_the_sqs_message_after_processing_succeeds(self):
        self._triggered_notification()

        evaluate_camera_image('b', 'k', 'cam-1', 'handle-abc')

        self.sqs_cls.return_value.delete_message.assert_called_once_with('handle-abc')

    def test_does_not_delete_the_message_when_processing_raises(self):
        """The whole point of deferring the delete: a failure must leave the
        event on the queue instead of dropping it."""
        self.process.side_effect = RuntimeError('model exploded')

        with self.assertRaises(RuntimeError):
            evaluate_camera_image('b', 'k', 'cam-1', 'handle-abc')

        self.sqs_cls.return_value.delete_message.assert_not_called()

    def test_does_not_delete_the_message_when_download_fails(self):
        self.storage.download_image.side_effect = OSError('gone')

        with self.assertRaises(Exception):
            evaluate_camera_image('b', 'k', 'cam-1', 'handle-abc')

        self.sqs_cls.return_value.delete_message.assert_not_called()

    def test_skips_deletion_when_no_receipt_handle_given(self):
        self._triggered_notification()

        evaluate_camera_image('b', 'k', 'cam-1')

        self.sqs_cls.return_value.delete_message.assert_not_called()

    def test_returns_the_number_of_notifications_created(self):
        self._triggered_notification('Person Detection', 'Dog Detection')

        # Two rules fired, but they were bundled into the one notification.
        self.assertEqual(evaluate_camera_image('b', 'k', 'cam-1'), 1)

    def test_returns_zero_when_no_rule_fired(self):
        self.assertEqual(evaluate_camera_image('b', 'k', 'cam-1'), 0)


class AttachVideoClipTests(TestCase):
    """A clip lands in S3 after the notification its detection still created, so
    the two are matched up by the uuid stem they share."""

    def setUp(self):
        sqs_patcher = patch.object(tasks, 'SQSImageQueueClient')
        storage_patcher = patch.object(tasks, 'get_s3_image_storage_client')
        self.sqs_cls = sqs_patcher.start()
        # An orphan clip is deleted from S3, so keep boto out of these tests.
        self.storage = storage_patcher.start().return_value
        self.addCleanup(sqs_patcher.stop)
        self.addCleanup(storage_patcher.stop)

        self.user = User.objects.create_user(
            username='alice', email='alice@example.com',
            password='StrongPass123!', first_name='Alice', last_name='Smith')
        self.camera = Camera.objects.create(owner=self.user, location='Front Door')
        self.rule = Rule.objects.create(
            owner=self.user, camera=self.camera,
            rule='a person is present', rule_nickname='Person Detection')
        self.camera_id = str(self.camera.public_camera_id)
        self.stem = '0e5f7a1c-2b3d-4e5f-8a9b-0c1d2e3f4a5b'
        self.notification = self._notification(self.stem, self.rule)

    def _notification(self, stem, *rules):
        notification = Notification.objects.create(
            camera=self.camera,
            rule_nicknames=[rule.rule_nickname for rule in rules],
            detection_image_key=detection_key(self.camera_id, stem))
        notification.rules.set(rules)
        return notification

    def _clip_key(self, stem=None):
        return clip_key(self.camera_id, stem or self.stem)

    def test_attaches_the_clip_to_the_notification_sharing_its_stem(self):
        attached = attach_video_clip('clip-bucket', self._clip_key(), self.camera_id)

        self.assertEqual(attached, 1)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.video_clip_key, self._clip_key())

    def test_attaches_the_clip_once_however_many_rules_fired(self):
        """One still can trigger several rules, but they share one notification,
        so the clip lands on that single row."""
        other_rule = Rule.objects.create(
            owner=self.user, camera=self.camera,
            rule='a dog is present', rule_nickname='Dog Detection')
        self.notification.rules.add(other_rule)

        attached = attach_video_clip('clip-bucket', self._clip_key(), self.camera_id)

        self.assertEqual(attached, 1)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.video_clip_key, self._clip_key())

    def test_does_not_touch_notifications_from_a_different_detection(self):
        unrelated = self._notification('some-other-stem', self.rule)

        attach_video_clip('clip-bucket', self._clip_key(), self.camera_id)

        unrelated.refresh_from_db()
        self.assertIsNone(unrelated.video_clip_key)

    def test_clip_with_no_matching_notification_is_not_an_error(self):
        """Routine: the camera records a clip for every event, including the
        ones where no rule fired and so no notification exists."""
        orphan_key = self._clip_key(stem='never-triggered-a-rule')

        attached = attach_video_clip('clip-bucket', orphan_key, self.camera_id)

        self.assertEqual(attached, 0)
        # Nothing will ever reference it, so it doesn't stay in the bucket.
        self.storage.delete_object.assert_called_once_with('clip-bucket', orphan_key)

    def test_does_not_attach_a_clip_across_cameras(self):
        other_camera = Camera.objects.create(owner=self.user, location='Garage')

        attached = attach_video_clip(
            'clip-bucket', clip_key(other_camera.public_camera_id, self.stem),
            str(other_camera.public_camera_id))

        self.assertEqual(attached, 0)
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.video_clip_key)

    def test_malformed_key_is_ignored_rather_than_raising(self):
        attached = attach_video_clip('clip-bucket', 'not-a-key', self.camera_id)

        self.assertEqual(attached, 0)

    def test_non_clip_key_is_ignored(self):
        attached = attach_video_clip(
            'clip-bucket', detection_key(self.camera_id, self.stem), self.camera_id)

        self.assertEqual(attached, 0)
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.video_clip_key)

    def test_deletes_the_sqs_message_after_attaching(self):
        attach_video_clip('clip-bucket', self._clip_key(), self.camera_id, 'handle-abc')

        self.sqs_cls.return_value.delete_message.assert_called_once_with('handle-abc')

    def test_deletes_the_sqs_message_even_when_nothing_matched(self):
        """An orphan clip must not be left on the queue to be redelivered forever."""
        attach_video_clip(
            'clip-bucket', self._clip_key(stem='no-match'), self.camera_id, 'handle-abc')

        self.sqs_cls.return_value.delete_message.assert_called_once_with('handle-abc')

    def test_skips_deletion_when_no_receipt_handle_given(self):
        attach_video_clip('clip-bucket', self._clip_key(), self.camera_id)

        self.sqs_cls.return_value.delete_message.assert_not_called()
