import pytest
from PIL import Image

from events.ml.base import UserRulesEvalRequest, RulesModel
from events.ml.base import RuleDTO


# --- RulesModelEvaluationInput ---

def test_stores_image_and_rules():
    image = Image.new('RGB', (10, 10))
    rules = [RuleDTO(public_rule_id='1', rule_name='Test', rule_text='a cat is present')]

    inp = UserRulesEvalRequest(image=image, rules=rules)

    assert inp.image is image
    assert inp.rules is rules


# --- RulesModel ---

def test_cannot_instantiate_without_implementing_abstract_methods():
    with pytest.raises(TypeError):
        RulesModel()


def test_subclass_implementing_both_methods_can_be_instantiated():
    class ConcreteRulesModel(RulesModel):
        def init(self):
            pass

        def evaluate_rules(self, eval_input):
            return []

    model = ConcreteRulesModel()
    assert model.evaluate_rules(None) == []
