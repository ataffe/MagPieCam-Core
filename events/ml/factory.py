"""Builds the rules model backend named by config.

Local development runs the self-hosted gemma4 model; the deployed service calls
the Gemini API.
"""
import logging

from events.ml.base import RulesModel

logger = logging.getLogger("[Rules Model Factory]")

API = "api"
HOSTED = "hosted"
MODEL_TYPES = (API, HOSTED)


def _required(ml_config: dict, key: str, model_type: str) -> str:
    """Fail at startup with the key name rather than deep in a backend later."""
    value = ml_config.get(key)
    if value is None or not str(value).strip():
        raise ValueError(
            f"ml.{key} is required when ml.model_type is '{model_type}'"
        )
    return str(value).strip()


def build_rules_model(ml_config: dict) -> RulesModel:
    """Construct the configured backend. Caller is responsible for init()."""
    model_type = str(ml_config.get("model_type") or API).strip().lower()

    if model_type == API:
        from events.ml.api.gemini import GeminiApiRulesModel
        model_name = _required(ml_config, "api_model_name", model_type)
        logger.info("Using Gemini API rules model (%s)", model_name)
        return GeminiApiRulesModel(model_name)

    if model_type == HOSTED:
        variant = _required(ml_config, "hosted_model_name", model_type)
        weights_dir = _required(ml_config, "model_weights_dir", model_type)
        try:
            from events.ml.hosted.gemma4 import Gemma4RulesModel
        except ImportError as e:
            raise ImportError(
                "The hosted rules model needs torch and transformers, which are "
                "only in requirements/hosted.txt because the deployed worker "
                "uses the API backend. Install that file to run locally. "
                f"({e})"
            ) from e
        logger.info("Using hosted gemma4 rules model (%s)", variant)
        return Gemma4RulesModel(
            model_variant=variant, model_weights_dir=weights_dir)

    raise ValueError(
        f"Unknown ml.model_type '{model_type}'. Expected one of: "
        f"{', '.join(MODEL_TYPES)}"
    )
