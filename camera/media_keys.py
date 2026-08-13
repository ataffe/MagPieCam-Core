"""Object-key formats for camera uploads.

A detection still and the clip recorded around the same event share one uuid
stem, so the two can be paired up later without any extra bookkeeping:

    detection/<public_camera_id>/<stem>.jpg
    clips/<public_camera_id>/<stem>.mp4

`parse_media_key` is the inverse, and is what lets an arriving clip find the
notification that its detection created.
"""
import uuid
from typing import NamedTuple

DETECTION_PREFIX = 'detection'
PREVIEW_PREFIX = 'preview'
CLIP_PREFIX = 'clips'


class ParsedMediaKey(NamedTuple):
    prefix: str
    public_camera_id: str
    stem: str
    extension: str


def new_stem() -> str:
    """The uuid a detection still and its clip are paired by."""
    return str(uuid.uuid4())


def detection_key(public_camera_id, stem: str) -> str:
    return f'{DETECTION_PREFIX}/{public_camera_id}/{stem}.jpg'


def preview_key(public_camera_id) -> str:
    return f'{PREVIEW_PREFIX}/{public_camera_id}/latest.jpg'


def clip_key(public_camera_id, stem: str, extension: str = 'mp4') -> str:
    return f'{CLIP_PREFIX}/{public_camera_id}/{stem}.{extension}'


def parse_media_key(key: str) -> ParsedMediaKey | None:
    """Split a key into its parts, or None if it isn't a well-formed media key."""
    if not key:
        return None
    parts = key.split('/')
    if len(parts) != 3:
        return None
    prefix, public_camera_id, filename = parts
    stem, separator, extension = filename.rpartition('.')
    if not (prefix and public_camera_id and stem and separator and extension):
        return None
    return ParsedMediaKey(prefix, public_camera_id, stem, extension)
