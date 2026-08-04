import json
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from events.ml.hosted.gemma4 import Gemma4RulesModel
from events.ml.base import UserRulesEvalRequest
from events.ml.base import RuleDTO


MODULE = 'events.ml.hosted.gemma4'


@pytest.fixture
def sample_rules():
    return [
        RuleDTO(
            public_rule_id='1',
            rule_name='Person Detection',
            rule_text='a person is present'),
        RuleDTO(
            public_rule_id='2',
            rule_name='Vehicle Detection',
            rule_text='a vehicle is present'),
    ]


@pytest.fixture
def sample_image():
    return Image.new('RGB', (100, 100), color=(128, 64, 32))


def _verdicts(*pairs) -> str:
    return json.dumps({"verdicts": [{"id": i, "verdict": v} for i, v in pairs]})


@pytest.fixture
def initialized_model():
    instance = Gemma4RulesModel(
        model_variant='test-variant', model_weights_dir='test_weights')
    instance.model = MagicMock()
    instance.processor = MagicMock()
    instance.processor.parse_response.return_value = {
        'content': _verdicts(('1', 'yes'), ('2', 'no'))}
    return instance


def _respond(model, raw: str) -> None:
    """Set the text the fake processor decodes out of the model's output."""
    model.processor.parse_response.return_value = {'content': raw}


def _user_message(model):
    messages = model.processor.apply_chat_template.call_args.args[0]
    return next(m for m in messages if m['role'] == 'user')


def _prompt_text(model) -> str:
    content = _user_message(model)['content']
    return next(c for c in content if c['type'] == 'text')['text']


# --- __init__ ---

def test_constructor_sets_variant_and_weights_dir():
    model = Gemma4RulesModel(
        model_variant='gemma4-e2b-it', model_weights_dir='ml_weights')
    assert model.variant == 'gemma4-e2b-it'
    assert model.weights_dir == 'ml_weights'


def test_constructor_leaves_model_and_processor_as_none():
    model = Gemma4RulesModel(model_variant='test', model_weights_dir='test')
    assert model.model is None
    assert model.processor is None


# --- init(): weight downloading ---

def test_init_skips_download_when_weights_are_present(tmp_path):
    (tmp_path / 'model.safetensors').touch()
    model = Gemma4RulesModel(
        model_variant='test-variant', model_weights_dir=str(tmp_path))
    with patch(f'{MODULE}.AutoModelForCausalLM'), \
         patch(f'{MODULE}.AutoProcessor'), \
         patch(f'{MODULE}.download_weights_backblaze') as mock_dl:
        model.init()
    mock_dl.assert_not_called()


def test_init_downloads_weights_when_dir_does_not_exist(tmp_path):
    weights_dir = str(tmp_path / 'nonexistent')
    model = Gemma4RulesModel(
        model_variant='test-variant', model_weights_dir=weights_dir)
    with patch(f'{MODULE}.AutoModelForCausalLM'), \
         patch(f'{MODULE}.AutoProcessor'), \
         patch(f'{MODULE}.download_weights_backblaze') as mock_dl:
        model.init()
    mock_dl.assert_called_once_with('gemma4', 'test-variant', weights_dir)


def test_init_downloads_weights_when_dir_is_empty(tmp_path):
    model = Gemma4RulesModel(
        model_variant='test-variant', model_weights_dir=str(tmp_path))
    with patch(f'{MODULE}.AutoModelForCausalLM'), \
         patch(f'{MODULE}.AutoProcessor'), \
         patch(f'{MODULE}.download_weights_backblaze') as mock_dl:
        model.init()
    mock_dl.assert_called_once_with('gemma4', 'test-variant', str(tmp_path))


# --- init(): model loading ---

def test_init_loads_model_with_bfloat16_and_auto_device_map(tmp_path):
    (tmp_path / 'model.safetensors').touch()
    model = Gemma4RulesModel(
        model_variant='test-variant', model_weights_dir=str(tmp_path))
    with patch(f'{MODULE}.AutoModelForCausalLM') as mock_cls, \
         patch(f'{MODULE}.AutoProcessor'), \
         patch(f'{MODULE}.torch') as mock_torch, \
         patch(f'{MODULE}.download_weights_backblaze'):
        model.init()
    mock_cls.from_pretrained.assert_called_once_with(
        str(tmp_path),
        dtype=mock_torch.bfloat16,
        device_map='auto',
        local_files_only=True,
    )


def test_init_loads_processor_from_weights_dir(tmp_path):
    (tmp_path / 'model.safetensors').touch()
    model = Gemma4RulesModel(
        model_variant='test-variant', model_weights_dir=str(tmp_path))
    with patch(f'{MODULE}.AutoModelForCausalLM'), \
         patch(f'{MODULE}.AutoProcessor') as mock_proc, \
         patch(f'{MODULE}.download_weights_backblaze'):
        model.init()
    mock_proc.from_pretrained.assert_called_once_with(
        str(tmp_path), local_files_only=True)


def test_init_assigns_loaded_model_and_processor_to_instance(tmp_path):
    (tmp_path / 'model.safetensors').touch()
    model = Gemma4RulesModel(
        model_variant='test-variant', model_weights_dir=str(tmp_path))
    with patch(f'{MODULE}.AutoModelForCausalLM') as mock_cls, \
         patch(f'{MODULE}.AutoProcessor') as mock_proc, \
         patch(f'{MODULE}.download_weights_backblaze'):
        model.init()
    assert model.model is mock_cls.from_pretrained.return_value
    assert model.processor is mock_proc.from_pretrained.return_value


def test_init_runs_warmup_generate(tmp_path):
    (tmp_path / 'model.safetensors').touch()
    model = Gemma4RulesModel(
        model_variant='test-variant', model_weights_dir=str(tmp_path))
    with patch(f'{MODULE}.AutoModelForCausalLM') as mock_cls, \
         patch(f'{MODULE}.AutoProcessor'), \
         patch(f'{MODULE}.download_weights_backblaze'):
        model.init()
    mock_cls.from_pretrained.return_value.generate.assert_called_once()


# --- _build_rule_messages ---

def test_build_rule_messages_includes_two_system_messages(
        initialized_model, sample_rules):
    messages = initialized_model._build_rule_messages(sample_rules)
    system_messages = [m for m in messages if m['role'] == 'system']
    assert len(system_messages) == 2


def test_build_rule_messages_creates_a_single_user_message_for_all_rules(
        initialized_model, sample_rules):
    messages = initialized_model._build_rule_messages(sample_rules)
    user_messages = [m for m in messages if m['role'] == 'user']
    assert len(user_messages) == 1


def test_build_rule_messages_attaches_the_image_exactly_once(
        initialized_model, sample_rules):
    messages = initialized_model._build_rule_messages(sample_rules)
    image_parts = [
        part
        for message in messages if isinstance(message['content'], list)
        for part in message['content'] if part['type'] == 'image'
    ]
    assert len(image_parts) == 1


def test_build_rule_messages_lists_every_rule_id_and_text(
        initialized_model, sample_rules):
    messages = initialized_model._build_rule_messages(sample_rules)
    user_message = next(m for m in messages if m['role'] == 'user')
    text = next(c for c in user_message['content'] if c['type'] == 'text')['text']
    assert '1:a person is present' in text
    assert '2:a vehicle is present' in text


def test_build_rule_messages_does_not_mutate_the_rule_dtos(initialized_model):
    rule = RuleDTO(public_rule_id='1', rule_name='Raccoon',
                   rule_text='Tell me when you see a raccoon')
    initialized_model._build_rule_messages([rule])
    assert rule.rule_text == 'Tell me when you see a raccoon'


# --- token budget ---

def test_token_budget_scales_with_rule_count(initialized_model):
    assert (initialized_model._token_budget(10)
            > initialized_model._token_budget(2))


def test_token_budget_honours_an_explicit_override():
    model = Gemma4RulesModel(
        model_variant='test', model_weights_dir='test', max_new_tokens=256)
    assert model._token_budget(99) == 256


# --- evaluate_rules ---

def test_evaluate_rules_makes_a_single_generate_call_for_all_rules(
        initialized_model, sample_rules, sample_image):
    initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert initialized_model.model.generate.call_count == 1


def test_evaluate_rules_applies_the_chat_template_once(
        initialized_model, sample_rules, sample_image):
    initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert initialized_model.processor.apply_chat_template.call_count == 1


def test_evaluate_rules_generates_greedily(
        initialized_model, sample_rules, sample_image):
    initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert initialized_model.model.generate.call_args.kwargs['do_sample'] is False


def test_evaluate_rules_passes_a_logits_processor_when_configured(
        initialized_model, sample_rules, sample_image):
    sentinel = object()
    initialized_model.logits_processor = sentinel
    initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert (initialized_model.model.generate.call_args.kwargs['logits_processor']
            is sentinel)


def test_evaluate_rules_omits_logits_processor_by_default(
        initialized_model, sample_rules, sample_image):
    initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert 'logits_processor' not in initialized_model.model.generate.call_args.kwargs


def test_evaluate_rules_sends_every_rule_in_one_prompt(
        initialized_model, sample_rules, sample_image):
    initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    text = _prompt_text(initialized_model)
    assert '1:a person is present' in text
    assert '2:a vehicle is present' in text


def test_evaluate_rules_returns_only_the_ids_with_a_yes_verdict(
        initialized_model, sample_rules, sample_image):
    _respond(initialized_model, _verdicts(('1', 'yes'), ('2', 'no')))
    result = initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert result == ['1']


def test_evaluate_rules_returns_all_triggered_ids(
        initialized_model, sample_rules, sample_image):
    _respond(initialized_model, _verdicts(('1', 'yes'), ('2', 'yes')))
    result = initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert result == ['1', '2']


def test_evaluate_rules_excludes_unsure_verdicts(
        initialized_model, sample_rules, sample_image):
    _respond(initialized_model, _verdicts(('1', 'unsure'), ('2', 'no')))
    result = initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert result == []


def test_evaluate_rules_tolerates_a_fenced_json_response(
        initialized_model, sample_rules, sample_image):
    _respond(initialized_model,
             '```json\n' + _verdicts(('1', 'yes')) + '\n```')
    result = initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert result == ['1']


def test_evaluate_rules_returns_empty_when_the_response_is_not_json(
        initialized_model, sample_rules, sample_image):
    _respond(initialized_model, 'I think I can see a person.')
    result = initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert result == []


def test_evaluate_rules_ignores_ids_that_were_not_asked_about(
        initialized_model, sample_rules, sample_image):
    _respond(initialized_model, _verdicts(('1', 'yes'), ('99', 'yes')))
    result = initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert result == ['1']


def test_evaluate_rules_with_no_rules_skips_generation(
        initialized_model, sample_image):
    result = initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=[]))
    assert result == []
    initialized_model.model.generate.assert_not_called()


def test_evaluate_rules_returns_empty_when_generation_raises(
        initialized_model, sample_rules, sample_image):
    initialized_model.model.generate.side_effect = RuntimeError('CUDA OOM')
    result = initialized_model.evaluate_rules(
        UserRulesEvalRequest(image=sample_image, rules=sample_rules))
    assert result == []
