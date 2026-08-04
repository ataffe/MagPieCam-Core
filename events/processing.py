"""Evaluates a camera's rules against an image and records what fired.
"""
import logging
from functools import lru_cache

from django.conf import settings

from camera.models import Camera
from events.ml.base import UserRulesEvalRequest
from events.ml.factory import build_rules_model
from events.selectors import get_rule_dtos_by_camera_ids
from notifications.models import Notification
from rules.models import Rule

logger = logging.getLogger('Events')


@lru_cache(maxsize=1)
def get_rules_model():
    """One model per worker process.
    """
    model = build_rules_model(settings.ML_CONFIG)
    model.init()
    return model


def create_notifications(public_camera_id: str, triggered_rule_ids: list[str]) -> list[Notification]:
    """Record one notification per rule that fired.

    Rules are re-queried scoped to this camera, so a model that echoes back an
    id belonging to someone else's camera can't create a notification on it.
    """
    if not triggered_rule_ids:
        return []

    camera = Camera.objects.filter(public_camera_id=public_camera_id).first()
    if camera is None:
        logger.warning('No camera found for %s; dropping %d triggered rule(s)',
                       public_camera_id, len(triggered_rule_ids))
        return []

    rules = Rule.objects.filter(
        public_rule_id__in=triggered_rule_ids, camera=camera)

    return Notification.objects.bulk_create(
        [Notification(camera=camera, rule=rule) for rule in rules])


def process_camera_image(public_camera_id: str, image) -> list[Notification]:
    """Evaluate one image against its camera's enabled rules."""
    rules = get_rule_dtos_by_camera_ids([public_camera_id]).get(public_camera_id, [])
    if not rules:
        logger.debug('No enabled rules for camera %s; nothing to evaluate',
                     public_camera_id)
        return []

    triggered_rule_ids = get_rules_model().evaluate_rules(
        UserRulesEvalRequest(image, rules))

    if not triggered_rule_ids:
        logger.info('No rules triggered for camera %s', public_camera_id)
        return []

    notifications = create_notifications(public_camera_id, triggered_rule_ids)
    logger.info('Created %d notification(s) for camera %s',
                len(notifications), public_camera_id)
    return notifications
