"""Reads the rules the processor evaluates, on the Django ORM.
"""
from collections import defaultdict

from events.ml.base import RuleDTO
from rules.models import Rule
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.db.models import Q


def get_rule_dtos_by_camera_ids(
        camera_public_ids: list[str]) -> dict[str, list[RuleDTO]]:
    """Map each requested camera's public id to its enabled rules.
    """
    rules_by_camera: dict[str, list[RuleDTO]] = defaultdict(
        list, {camera_public_id: [] for camera_public_id in camera_public_ids})

    cooldown_cutoff = timezone.now() - timedelta(minutes=settings.RULE_TRIGGER_COOLDOWN_MINUTES)
    rows = (
        Rule.objects
        .filter(is_enabled=True,
                camera__public_camera_id__in=camera_public_ids)
        .filter(Q(last_triggered__isnull=True) | Q(last_triggered__lt=cooldown_cutoff))
        .select_related('camera')
    )

    for rule in rows:
        rules_by_camera[str(rule.camera.public_camera_id)].append(
            RuleDTO(
                public_rule_id=str(rule.public_rule_id),
                rule_name=rule.rule_nickname,
                rule_text=rule.rule,
            )
        )

    return dict(rules_by_camera)
