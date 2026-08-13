from django.test import SimpleTestCase

from camera.media_keys import (
    clip_key, detection_key, new_stem, parse_media_key, preview_key,
)


class MediaKeyTests(SimpleTestCase):
    def test_detection_and_clip_keys_pair_on_a_shared_stem(self):
        """The whole scheme rests on this: given one key you can name the other."""
        stem = new_stem()

        parsed_detection = parse_media_key(detection_key('cam-1', stem))
        parsed_clip = parse_media_key(clip_key('cam-1', stem))

        self.assertEqual(parsed_detection.stem, parsed_clip.stem)
        self.assertNotEqual(parsed_detection.prefix, parsed_clip.prefix)

    def test_new_stem_is_unique_per_call(self):
        self.assertNotEqual(new_stem(), new_stem())

    def test_parse_detection_key(self):
        parsed = parse_media_key('detection/cam-1/abc.jpg')

        self.assertEqual(parsed.prefix, 'detection')
        self.assertEqual(parsed.public_camera_id, 'cam-1')
        self.assertEqual(parsed.stem, 'abc')
        self.assertEqual(parsed.extension, 'jpg')

    def test_clip_key_defaults_to_mp4(self):
        self.assertEqual(clip_key('cam-1', 'abc'), 'clips/cam-1/abc.mp4')

    def test_clip_key_honours_an_explicit_extension(self):
        self.assertEqual(clip_key('cam-1', 'abc', 'jpg'), 'clips/cam-1/abc.jpg')

    def test_preview_key_is_fixed_per_camera(self):
        self.assertEqual(preview_key('cam-1'), 'preview/cam-1/latest.jpg')

    def test_stem_keeps_inner_dots(self):
        # rpartition splits on the *last* dot, so a stem containing dots
        # survives intact rather than being truncated at the first one.
        parsed = parse_media_key('clips/cam-1/a.b.c.mp4')

        self.assertEqual(parsed.stem, 'a.b.c')
        self.assertEqual(parsed.extension, 'mp4')

    def test_malformed_keys_parse_to_none(self):
        for key in ('', 'not-a-key', 'too/few', 'too/many/parts/here',
                    'detection/cam-1/no-extension', 'detection/cam-1/.jpg',
                    'detection//abc.jpg', '/cam-1/abc.jpg'):
            with self.subTest(key=key):
                self.assertIsNone(parse_media_key(key))
