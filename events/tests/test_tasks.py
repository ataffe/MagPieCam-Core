from unittest.mock import MagicMock, patch

from django.test import TestCase

from events import tasks
from events.tasks import evaluate_camera_image


class EvaluateCameraImageTests(TestCase):
    def setUp(self):
        storage_patcher = patch.object(tasks, 'S3ImageStorageClient')
        sqs_patcher = patch.object(tasks, 'SQSImageQueueClient')
        processing_patcher = patch.object(tasks, 'process_camera_image')
        self.storage_cls = storage_patcher.start()
        self.sqs_cls = sqs_patcher.start()
        self.process = processing_patcher.start()
        self.addCleanup(storage_patcher.stop)
        self.addCleanup(sqs_patcher.stop)
        self.addCleanup(processing_patcher.stop)

        self.process.return_value = []

    def test_downloads_the_object_named_in_the_event(self):
        evaluate_camera_image('my-bucket', 'detect/cam-1/img.jpg', 'cam-1')

        self.storage_cls.return_value.download_image.assert_called_once_with(
            'my-bucket', 'detect/cam-1/img.jpg')

    def test_passes_downloaded_image_to_processing(self):
        image = self.storage_cls.return_value.download_image.return_value

        evaluate_camera_image('my-bucket', 'detect/cam-1/img.jpg', 'cam-1')

        self.process.assert_called_once_with('cam-1', image)

    def test_deletes_the_sqs_message_after_processing_succeeds(self):
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
        self.storage_cls.return_value.download_image.side_effect = OSError('gone')

        with self.assertRaises(Exception):
            evaluate_camera_image('b', 'k', 'cam-1', 'handle-abc')

        self.sqs_cls.return_value.delete_message.assert_not_called()

    def test_skips_deletion_when_no_receipt_handle_given(self):
        evaluate_camera_image('b', 'k', 'cam-1')

        self.sqs_cls.return_value.delete_message.assert_not_called()

    def test_returns_the_number_of_notifications_created(self):
        self.process.return_value = [MagicMock(), MagicMock()]

        self.assertEqual(evaluate_camera_image('b', 'k', 'cam-1'), 2)
