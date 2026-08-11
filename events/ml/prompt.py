"""Prompt construction and verdict parsing shared by the hosted and API rules models.

Both backends ask one question about one image: which of the user's rules are
visible in it? Keeping the wording, the id/verdict contract, and the parsing in
one place stops the two from drifting apart when a prompt gets tuned.

The API backend constrains the response with a real JSON schema server-side; the
hosted backend can only ask nicely (see gemma4_rules_model), so the parser here
is deliberately tolerant of the wrappers small local models like to add.
"""
import json
import logging
import re

from typing import Optional
from events.ml.base import RuleDTO
from events.ml.base import RuleEvalResult


SYSTEM_INSTRUCTIONS = (
    "You evaluate whether a condition is present in a security camera image. "
    "Answer only from what is visibly present. If the image is too dark, "
    "blurry, or ambiguous to tell, answer 'unsure' rather than guessing."
)

RULES_PREAMBLE = (
    "For each condition below, answer whether it is visible in the image.\n"
)

# Only needed by backends that cannot enforce a response schema. The API backend
# passes RuleEvalResult's JSON schema instead and never sends this.
# TODO: User lm-format-enforcer etc.
JSON_RESPONSE_INSTRUCTIONS = (
    'Reply with JSON and nothing else. No prose, no explanation, no code fences. '
    'Use exactly this shape:\n'
    '{"verdicts": [{"id": "<rule id>", "verdict": "yes"}]}\n'
    'Each verdict must be one of "yes", "no", or "unsure". Include exactly one entry '
    'for every rule id listed, copying each id character for character.'
)

_CODE_FENCE = re.compile(r"```(?:json)?", re.IGNORECASE)


def normalize_rule_text(rule_text: str) -> str:
    """Rules are user-authored, so they arrive phrased as standing instructions
    ("Tell me when you see a raccoon"). The models answer more consistently when
    the text reads as a question about the current frame.
    """
    return rule_text.strip().replace("Tell me when you see", "Is there")


def build_rules_list(rules: list[RuleDTO]) -> str:
    """Build a single string containing all rules, separated by newlines.
        e.g. 1234:a cat eating.
             6789:someone tampering with the door.
             1011:a person with a package.

    The id prefix is what lets one response cover every rule: the model echoes
    the id back with its verdict, so we never depend on answer ordering.
    """
    return "".join(
        f"{rule.public_rule_id}:{normalize_rule_text(rule.rule_text)}\n"
        for rule in rules
    )


def parse_rule_eval_result(raw: str, logger: logging.Logger) -> Optional[RuleEvalResult]:
    """Recover a RuleEvalResult from raw model output, or None if it isn't there.

    Tolerates the three things local models do even when told not to: wrapping the
    JSON in a code fence, padding it with a sentence of prose, and returning the
    bare verdict list without the object around it.
    """
    if not raw or not raw.strip():
        return None

    candidate = _CODE_FENCE.sub("", raw).strip().strip("`").strip()

    # Attempt to extract json from the response.
    start = min((i for i in (candidate.find("{"), candidate.find("[")) if i != -1), default=-1)
    end = max(candidate.rfind("}"), candidate.rfind("]"))
    if start == -1 or end <= start:
        logger.warning("No JSON found in model output | raw=%r", raw[:200])
        return None

    try:
        payload = json.loads(candidate[start:end + 1])
    except json.JSONDecodeError as e:
        logger.warning("Model output was not valid JSON: %s | raw=%r", e, raw[:200])
        return None

    # A bare list of verdicts is a common near-miss; accept it.
    if isinstance(payload, list):
        payload = {"verdicts": payload}
    if not isinstance(payload, dict):
        logger.warning("Model output JSON was not an object | raw=%r", raw[:200])
        return None

    # Convert "Yes"/"YES" to "yes"
    for verdict in payload.get("verdicts") or []:
        if isinstance(verdict, dict) and isinstance(verdict.get("verdict"), str):
            verdict["verdict"] = verdict["verdict"].strip().lower()

    try:
        return RuleEvalResult.model_validate(payload)
    except Exception as e:
        logger.warning("Model output did not match schema: %s | raw=%r", e, raw[:200])
        return None


def triggered_rule_ids(
        eval_results: RuleEvalResult,
        logger: logging.Logger,
        valid_ids: Optional[set[str]] = None) -> list[str]:
    """Reduce verdicts to the ids that fired.

    'unsure' deliberately does not trigger: a false alert on a dark frame costs
    the user more than a missed one, and the system instructions tell the model
    to prefer 'unsure' over guessing.

    When valid_ids is given, ids the caller never asked about are dropped -- a
    model that invents an id would otherwise KeyError the caller's rule lookup.
    """
    triggered = []
    for rule_verdict in eval_results.verdicts:
        if valid_ids is not None and rule_verdict.id not in valid_ids:
            logger.warning("Ignoring verdict for unknown rule id %s", rule_verdict.id)
            continue
        if rule_verdict.verdict == "yes":
            triggered.append(rule_verdict.id)
            logger.info("Rule %s triggered (verdict=%s)", rule_verdict.id, rule_verdict.verdict)
        elif rule_verdict.verdict == "no":
            logger.debug("Rule %s not triggered (verdict=%s)", rule_verdict.id, rule_verdict.verdict)
        else:
            logger.info("Rule %s unsure (verdict=%s)", rule_verdict.id, rule_verdict.verdict)
    return triggered