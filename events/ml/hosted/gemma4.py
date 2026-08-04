import torch
from transformers import AutoProcessor, AutoModelForCausalLM
import logging
from pathlib import Path

from typing import Optional
from events.ml.base import UserRulesEvalRequest, RulesModel
from events.ml.prompt import (
    JSON_RESPONSE_INSTRUCTIONS,
    RULES_PREAMBLE,
    SYSTEM_INSTRUCTIONS,
    build_rules_list,
    parse_rule_eval_result,
    triggered_rule_ids,
)
from events.ml.weights import download_weights_backblaze
from events.ml.base import RuleDTO

logger = logging.getLogger("[Gemma4 Rules Model]")

# Roughly what one {"id": "<uuid>", "verdict": "unsure"} entry costs, plus room
# for the object around it. Beats a flat cap, which either truncates the JSON on
# a camera with many rules or wastes decode time on a camera with two.
_TOKENS_PER_VERDICT = 48
_TOKEN_OVERHEAD = 64


class Gemma4RulesModel(RulesModel):
    def __init__(
            self,
            model_variant: str,
            model_weights_dir: str,
            max_new_tokens: Optional[int] = None,
            logits_processor=None):
        self.model = None
        self.processor = None
        self.variant = model_variant
        self.weights_dir = model_weights_dir
        # Overrides the per-rule token budget, if set
        self.max_new_tokens = max_new_tokens

        # TODO: Use lm-format-enforcer or xgrammar etc. to enforce the JSON schema,
        #  and remove the parse_rule_eval_result fallback.
        self.logits_processor = logits_processor

    def init(self):
        model_path = self.weights_dir
        if (not Path(model_path).exists()
                or not any(Path(model_path).iterdir())):
            download_weights_backblaze('gemma4', self.variant, self.weights_dir)
            logger.info(f"Model downloaded to {model_path}")
        # model_path is a local directory populated by download_weights_backblaze
        # above, never a Hub repo id, so there's no revision to pin.
        self.model = AutoModelForCausalLM.from_pretrained(  # nosec B615
            model_path,
            dtype=torch.bfloat16,
            device_map="auto",
            local_files_only=True,
        )
        self.processor = AutoProcessor.from_pretrained(  # nosec B615
            model_path, local_files_only=True)

        warm_up_message = [
            {"role": "system", "content": "You are a helpful assistant."}
        ]
        text = self.processor.apply_chat_template(
            warm_up_message,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False
        )
        logger.info("Warming up model...")
        inputs = self.processor(
            text=text, return_tensors="pt").to(self.model.device)
        self.model.generate(**inputs, max_new_tokens=1024)
        logger.info("Warm up complete")

    @staticmethod
    def _build_rule_messages(rules: list[RuleDTO]) -> list[dict]:
        """The image is attached once. Previously each rule got its own turn and its
        own forward pass, which re-encoded the same frame per rule.
        """
        return [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "system", "content": JSON_RESPONSE_INSTRUCTIONS},
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text",
                     "text": RULES_PREAMBLE + build_rules_list(rules)},
                ],
            },
        ]

    def _token_budget(self, rule_count: int) -> int:
        if self.max_new_tokens is not None:
            return self.max_new_tokens
        return _TOKEN_OVERHEAD + _TOKENS_PER_VERDICT * rule_count

    def _generate(self, prompt_text: str, image, rule_count: int) -> str:
        """Run one forward pass and return the model's decoded reply."""
        inputs = self.processor(
            text=prompt_text, images=image,
            return_tensors="pt").to(self.model.device)

        input_len = inputs["input_ids"].shape[-1]
        generate_kwargs = {
            # Greedy: a rules evaluator should give the same verdict twice for
            # the same frame, and sampling buys nothing on a JSON response.
            "do_sample": False,
            "max_new_tokens": self._token_budget(rule_count),
        }
        if self.logits_processor is not None:
            generate_kwargs["logits_processor"] = self.logits_processor

        outputs = self.model.generate(**inputs, **generate_kwargs)
        response = self.processor.decode(
            outputs[0][input_len:], skip_special_tokens=False)
        return self.processor.parse_response(response).get('content', '')

    def evaluate_rules(self, user_rules_eval_request: UserRulesEvalRequest) -> list[str]:
        rules = user_rules_eval_request.rules
        if not rules:
            return []

        try:
            rule_messages = self._build_rule_messages(rules)
            prompt_text = self.processor.apply_chat_template(
                rule_messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False
            )
            raw = self._generate(
                prompt_text, user_rules_eval_request.image, len(rules))

            eval_results = parse_rule_eval_result(raw, logger)
            if eval_results is None:
                return []
            return triggered_rule_ids(
                eval_results, logger,
                valid_ids={rule.public_rule_id for rule in rules})
        except Exception as e:
            logger.exception(f"Unexpected error evaluating rules: {e}")
            return []