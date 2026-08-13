from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

import events.management.commands.consume_events as consume_events


def _message(bucket='my-bucket', key='detect/cam-1/img.jpg',
             public_camera_id='cam-1', receipt_handle='handle-1'):
    message = MagicMock()
    message.bucket = bucket
    message.key = key
    message.public_camera_id = public_camera_id
    message.receipt_handle = receipt_handle
    return message


class ConsumeEventsCommandTests(TestCase):
    def setUp(self):
        queue_patcher = patch.object(consume_events, 'SQSImageQueueClient')
        task_patcher = patch.object(consume_events, 'evaluate_camera_image')
        clip_task_patcher = patch.object(consume_events, 'attach_video_clip')
        self.queue_cls = queue_patcher.start()
        self.task = task_patcher.start()
        self.clip_task = clip_task_patcher.start()
        self.addCleanup(queue_patcher.stop)
        self.addCleanup(task_patcher.stop)
        self.addCleanup(clip_task_patcher.stop)

    def _set_messages(self, *messages):
        self.queue_cls.return_value.get_parsed_messages.return_value = list(messages)

    def test_dispatches_a_task_per_message(self):
        self._set_messages(_message(), _message(key='detect/cam-1/other.jpg'))

        call_command('consume_events', '--once')

        self.assertEqual(self.task.delay.call_count, 2)

    def test_passes_event_details_through_to_the_task(self):
        self._set_messages(_message())

        call_command('consume_events', '--once')

        self.task.delay.assert_called_once_with(
            'my-bucket', 'detect/cam-1/img.jpg', 'cam-1', 'handle-1')

    def test_empty_batch_dispatches_nothing(self):
        self._set_messages()

        call_command('consume_events', '--once')

        self.task.delay.assert_not_called()

    def test_does_not_delete_messages_itself(self):
        """Deletion belongs to the task, after the work commits -- the consumer
        must not ack the event merely for having enqueued it."""
        self._set_messages(_message())

        call_command('consume_events', '--once')

        self.queue_cls.return_value.delete_message.assert_not_called()

    @override_settings(AWS_VIDEO_CLIP_BUCKET='clip-bucket')
    def test_clip_bucket_events_go_to_the_clip_task_not_the_image_pipeline(self):
        """Both buckets share one queue, but an mp4 handed to the image pipeline
        would fail to decode and retry until it hit the DLQ."""
        self._set_messages(_message(bucket='clip-bucket', key='clips/cam-1/abc.mp4'))

        call_command('consume_events', '--once')

        self.clip_task.delay.assert_called_once_with(
            'clip-bucket', 'clips/cam-1/abc.mp4', 'cam-1', 'handle-1')
        self.task.delay.assert_not_called()

    @override_settings(AWS_VIDEO_CLIP_BUCKET='clip-bucket')
    def test_detection_bucket_events_still_go_to_the_image_pipeline(self):
        self._set_messages(_message(bucket='detection-bucket'))

        call_command('consume_events', '--once')

        self.task.delay.assert_called_once()
        self.clip_task.delay.assert_not_called()

    @override_settings(AWS_VIDEO_CLIP_BUCKET='clip-bucket')
    def test_a_mixed_batch_is_routed_per_message(self):
        self._set_messages(
            _message(bucket='detection-bucket'),
            _message(bucket='clip-bucket', key='clips/cam-1/abc.mp4'),
        )

        call_command('consume_events', '--once')

        self.assertEqual(self.task.delay.call_count, 1)
        self.assertEqual(self.clip_task.delay.call_count, 1)
