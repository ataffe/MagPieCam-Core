import io
import logging
import time
import random
import base64

from typing import Optional
from events.ml.base import UserRulesEvalRequest, RulesModel, RuleEvalResult
from events.ml.prompt import (
    RULES_PREAMBLE,
    SYSTEM_INSTRUCTIONS,
    build_rules_list,
    parse_rule_eval_result,
    triggered_rule_ids,
)
from google import genai
from google.genai import errors
from PIL import Image


logger = logging.getLogger("[Gemini Api Rules Model]")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

def _encode_image(image: Image.Image) -> tuple[str, str]:
    """Inline base64 instead of the Files API.
    """
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8"), "image/jpeg"


class GeminiApiRulesModel(RulesModel):
    def __init__(self, model_name: str, max_retries: int = 3):
        self.client = genai.Client()
        self.model_name = model_name
        self.max_retries = max_retries
        self.system_instructions = SYSTEM_INSTRUCTIONS

    def init(self):
        pass

    def _create_interaction(self, *, image_b64: str, mime_type: str, numbered_rule_list : str):
        """Call the API, retrying only genuinely transient failures."""
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                return self.client.interactions.create(
                    model=self.model_name,
                    system_instruction=self.system_instructions,
                    input=[
                        {
                            "type": "image",
                            "mime_type": mime_type,
                            "data": image_b64,
                        },
                        {"type": "text", "text": RULES_PREAMBLE + numbered_rule_list},
                    ],
                    response_format=[
                        {
                            "type": "text",
                            "mime_type": "application/json",
                            "schema": RuleEvalResult.model_json_schema(),
                        }
                    ],
                )

            except errors.APIError as e:
                last_error = e
                if e.code not in RETRYABLE_STATUS or attempt == self.max_retries:
                    logger.error(
                        "Gemini API error (code=%s, attempt=%d): %s",
                        e.code, attempt + 1, e.message,
                    )
                    raise

                delay = min(2 ** attempt + random.uniform(0, 0.5), 30.0)
                logger.warning(
                    "Gemini transient error %s, retrying in %.1fs (attempt %d/%d)",
                    e.code, delay, attempt + 1, self.max_retries,
                )
                time.sleep(delay)

        raise last_error

    @staticmethod
    def _get_triggered_rules(interaction, valid_ids: set[str]) -> list[str]:
        """Reduce the interaction's JSON body to the rule ids that fired."""
        raw = getattr(interaction, "output_text", None)
        if not raw:
            logger.warning("Gemini returned no output text; interaction=%s",
                           getattr(interaction, "id", "<no id>"))
            return []

        eval_results = parse_rule_eval_result(raw, logger)
        if eval_results is None:
            return []
        return triggered_rule_ids(eval_results, logger, valid_ids=valid_ids)


    def evaluate_rules(self, user_rules_eval_request: UserRulesEvalRequest) -> list[str]:
        rules = user_rules_eval_request.rules
        if not rules:
            return []

        image_b64, mime_type = _encode_image(user_rules_eval_request.image)
        try:
            numbered_rules = build_rules_list(rules)
            interaction = self._create_interaction(
                image_b64=image_b64,
                mime_type=mime_type,
                numbered_rule_list=numbered_rules,
            )
            return self._get_triggered_rules(
                interaction, {rule.public_rule_id for rule in rules})
        except Exception as e:
            logger.exception(f"Unexpected error evaluating rules for user: {e}")
            return []