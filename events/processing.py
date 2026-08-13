"""Evaluates a camera's rules against an image and records what fired.
"""
import logging
from datetime import timedelta
from functools import lru_cache

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from camera.models import Camera
from events.ml.base import UserRulesEvalRequest
from events.ml.model_factory import build_rules_model
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


def create_notification(public_camera_id: str, triggered_rule_ids: list[str],
                        detection_image_key: str | None = None) -> Notification | None:
    """Bundle every rule that fired on one image into a single notification.

    All the rules triggered by one detection image share that image and its
    clip, so they belong together in one notification rather than one each.
    Rules still cooling down are left out of the bundle.
    """
    if not triggered_rule_ids:
        return None

    camera = Camera.objects.filter(public_camera_id=public_camera_id).first()
    if camera is None:
        logger.warning('No camera found for %s; dropping %d triggered rule(s)',
                       public_camera_id, len(triggered_rule_ids))
        return None

    cooldown_cutoff = timezone.now() - timedelta(minutes=settings.RULE_TRIGGER_COOLDOWN_MINUTES)

    # Locks the candidate rows for the life of the transaction
    # so other workers can't modify the same rule at the same time.
    with transaction.atomic():
        # Ordered by id so rule_nicknames and the push body list the rules
        # in the same, stable order.
        rules = list(
            Rule.objects.select_for_update()
            .filter(public_rule_id__in=triggered_rule_ids, camera=camera)
            .filter(Q(last_triggered__isnull=True) | Q(last_triggered__lt=cooldown_cutoff))
            .order_by('id')
        )

        if not rules:
            return None

        Rule.objects.filter(id__in=[rule.id for rule in rules]).update(last_triggered=timezone.now())

        notification = Notification.objects.create(
            camera=camera,
            rule_nicknames=[rule.rule_nickname for rule in rules],
            detection_image_key=detection_image_key,
        )
        notification.rules.set(rules)
        return notification


def process_camera_image(public_camera_id: str, image,
                         detection_image_key: str | None = None) -> Notification | None:
    """Evaluate one image against its camera's enabled rules."""
    rules = get_rule_dtos_by_camera_ids([public_camera_id]).get(public_camera_id, [])
    if not rules:
        logger.debug('No enabled rules for camera %s; nothing to evaluate',
                     public_camera_id)
        return None

    triggered_rule_ids = get_rules_model().evaluate_rules(
        UserRulesEvalRequest(image, rules))

    if not triggered_rule_ids:
        logger.info('No rules triggered for camera %s', public_camera_id)
        return None

    notification = create_notification(public_camera_id, triggered_rule_ids, detection_image_key)
    if notification is None:
        logger.info('No notification created for camera %s', public_camera_id)
    else:
        logger.info('Created notification bundling %d rule(s) for camera %s',
                    len(notification.rule_nicknames), public_camera_id)
    return notification
