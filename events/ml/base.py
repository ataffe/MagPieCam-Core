"""The rules-model contract, and the input types it is defined over.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image
from pydantic import BaseModel
from typing import Literal


@dataclass
class RuleDTO:
    public_rule_id: str
    rule_name: str
    rule_text: str


class UserRulesEvalRequest:
    def __init__(self, image: Image.Image, rules: list[RuleDTO]):
        self.image: Image.Image = image
        self.rules: list[RuleDTO] = rules


class RulesModel(ABC):
    @abstractmethod
    def init(self):
        pass

    @abstractmethod
    def evaluate_rules(
            self,
            user_rules_eval_request: UserRulesEvalRequest) -> list[str]:
        pass


class RuleVerdict(BaseModel):
    id: str
    verdict: Literal["yes", "no", "unsure"]


class RuleEvalResult(BaseModel):
    verdicts: list[RuleVerdict]
