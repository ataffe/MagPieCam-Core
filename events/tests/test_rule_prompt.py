import json
import logging
import pytest

from events.ml.base import RuleDTO
from events.ml.prompt import (
    build_rules_list,
    normalize_rule_text,
    parse_rule_eval_result,
    triggered_rule_ids,
)
from events.ml.base import RuleEvalResult


logger = logging.getLogger("test")


@pytest.fixture
def sample_rules():
    return [
        RuleDTO(public_rule_id='1', rule_name='Person', rule_text='a person is present'),
        RuleDTO(public_rule_id='2', rule_name='Vehicle', rule_text='a vehicle is present'),
    ]


def _result(*pairs) -> str:
    return json.dumps({"verdicts": [{"id": i, "verdict": v} for i, v in pairs]})


# --- normalize_rule_text ---

def test_normalize_rewrites_standing_instruction_as_question():
    assert normalize_rule_text(
        'Tell me when you see a raccoon') == 'Is there a raccoon'


def test_normalize_strips_surrounding_whitespace():
    assert normalize_rule_text('  a person is present \n') == 'a person is present'


def test_normalize_leaves_unrelated_text_alone():
    assert normalize_rule_text('a vehicle is present') == 'a vehicle is present'


# --- build_rules_list ---

def test_build_rules_list_emits_one_id_prefixed_line_per_rule(sample_rules):
    lines = build_rules_list(sample_rules).strip().split('\n')
    assert lines == ['1:a person is present', '2:a vehicle is present']


def test_build_rules_list_does_not_mutate_the_rule_dtos():
    rule = RuleDTO(public_rule_id='1', rule_name='Raccoon',
                   rule_text='Tell me when you see a raccoon')
    build_rules_list([rule])
    assert rule.rule_text == 'Tell me when you see a raccoon'


def test_build_rules_list_with_no_rules_is_empty():
    assert build_rules_list([]) == ''


# --- parse_rule_eval_result ---

def test_parse_accepts_clean_json():
    result = parse_rule_eval_result(_result(('1', 'yes')), logger)
    assert result.verdicts[0].id == '1'
    assert result.verdicts[0].verdict == 'yes'


def test_parse_accepts_json_wrapped_in_a_code_fence():
    raw = '```json\n' + _result(('1', 'no')) + '\n```'
    result = parse_rule_eval_result(raw, logger)
    assert result.verdicts[0].verdict == 'no'


def test_parse_accepts_json_padded_with_prose():
    raw = 'Sure! Here are the verdicts:\n' + _result(('1', 'yes')) + '\nHope that helps.'
    result = parse_rule_eval_result(raw, logger)
    assert result.verdicts[0].verdict == 'yes'


def test_parse_accepts_a_bare_verdict_list():
    raw = json.dumps([{"id": "1", "verdict": "yes"}])
    result = parse_rule_eval_result(raw, logger)
    assert result.verdicts[0].id == '1'


def test_parse_lowercases_verdict_casing():
    raw = json.dumps({"verdicts": [{"id": "1", "verdict": "YES"}]})
    result = parse_rule_eval_result(raw, logger)
    assert result.verdicts[0].verdict == 'yes'


def test_parse_returns_none_for_prose_with_no_json():
    assert parse_rule_eval_result('I cannot tell from this image.', logger) is None


def test_parse_returns_none_for_malformed_json():
    assert parse_rule_eval_result('{"verdicts": [', logger) is None


def test_parse_returns_none_for_empty_output():
    assert parse_rule_eval_result('', logger) is None


def test_parse_returns_none_when_verdict_is_not_in_the_schema():
    raw = json.dumps({"verdicts": [{"id": "1", "verdict": "maybe"}]})
    assert parse_rule_eval_result(raw, logger) is None


# --- triggered_rule_ids ---

def test_triggered_returns_only_yes_verdicts():
    result = RuleEvalResult.model_validate_json(
        _result(('1', 'yes'), ('2', 'no'), ('3', 'unsure')))
    assert triggered_rule_ids(result, logger) == ['1']


def test_triggered_treats_unsure_as_not_triggered():
    result = RuleEvalResult.model_validate_json(_result(('1', 'unsure')))
    assert triggered_rule_ids(result, logger) == []


def test_triggered_drops_ids_the_caller_did_not_ask_about():
    result = RuleEvalResult.model_validate_json(
        _result(('1', 'yes'), ('hallucinated', 'yes')))
    assert triggered_rule_ids(result, logger, valid_ids={'1'}) == ['1']


def test_triggered_keeps_all_ids_when_no_filter_is_given():
    result = RuleEvalResult.model_validate_json(
        _result(('1', 'yes'), ('unexpected', 'yes')))
    assert triggered_rule_ids(result, logger) == ['1', 'unexpected']
