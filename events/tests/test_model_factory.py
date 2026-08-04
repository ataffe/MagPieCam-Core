import pytest
from unittest.mock import MagicMock, patch

from events.ml.factory import build_rules_model


API_CONFIG = {'model_type': 'api', 'api_model_name': 'gemini-3.1-flash-lite'}
HOSTED_CONFIG = {
    'model_type': 'hosted',
    'hosted_model_name': 'gemma4-e2b-it',
    'model_weights_dir': 'ml_weights',
}


@pytest.fixture
def mock_api_model():
    with patch('events.ml.api.gemini.GeminiApiRulesModel') as mock:
        yield mock


@pytest.fixture
def mock_hosted_model():
    with patch('events.ml.hosted.gemma4.Gemma4RulesModel') as mock:
        yield mock


# --- backend selection ---

def test_builds_the_api_model_when_configured(mock_api_model):
    model = build_rules_model(API_CONFIG)
    mock_api_model.assert_called_once_with('gemini-3.1-flash-lite')
    assert model is mock_api_model.return_value


def test_builds_the_hosted_model_when_configured(mock_hosted_model):
    model = build_rules_model(HOSTED_CONFIG)
    mock_hosted_model.assert_called_once_with(
        model_variant='gemma4-e2b-it', model_weights_dir='ml_weights')
    assert model is mock_hosted_model.return_value


def test_defaults_to_the_api_model_when_model_type_is_absent(mock_api_model):
    build_rules_model({'api_model_name': 'gemini-3.1-flash-lite'})
    mock_api_model.assert_called_once()


def test_defaults_to_the_api_model_when_model_type_is_blank(mock_api_model):
    build_rules_model({'model_type': '', 'api_model_name': 'gemini-3.1-flash-lite'})
    mock_api_model.assert_called_once()


def test_model_type_is_case_and_whitespace_insensitive(mock_hosted_model):
    build_rules_model({**HOSTED_CONFIG, 'model_type': '  Hosted '})
    mock_hosted_model.assert_called_once()


def test_rejects_an_unknown_model_type():
    with pytest.raises(ValueError, match='Unknown ml.model_type'):
        build_rules_model({'model_type': 'onnx'})


# --- required keys ---

def test_api_model_requires_model_name():
    with pytest.raises(ValueError, match='ml.api_model_name is required'):
        build_rules_model({'model_type': 'api'})


def test_api_model_rejects_a_blank_model_name():
    with pytest.raises(ValueError, match='ml.api_model_name is required'):
        build_rules_model({'model_type': 'api', 'api_model_name': '   '})


def test_hosted_model_requires_a_variant_name():
    with pytest.raises(ValueError, match='ml.hosted_model_name is required'):
        build_rules_model(
            {'model_type': 'hosted', 'model_weights_dir': 'ml_weights'})


def test_hosted_model_requires_a_weights_dir():
    with pytest.raises(ValueError, match='ml.model_weights_dir is required'):
        build_rules_model(
            {'model_type': 'hosted', 'hosted_model_name': 'gemma4-e2b-it'})


# --- deferred imports ---

def test_api_path_does_not_import_the_hosted_backend(mock_api_model):
    """The deployed service has no torch/transformers, so building the API model
    must not reach the hosted module's imports."""
    import sys
    with patch.dict(sys.modules):
        sys.modules.pop('events.ml.hosted.gemma4', None)
        build_rules_model(API_CONFIG)
        assert 'events.ml.hosted.gemma4' not in sys.modules


def test_hosted_path_reports_missing_deps_as_an_actionable_import_error():
    import builtins
    real_import = builtins.__import__

    def fail_on_transformers(name, *args, **kwargs):
        if name.startswith('events.ml.hosted'):
            raise ImportError("No module named 'transformers'")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, '__import__', side_effect=fail_on_transformers):
        with pytest.raises(ImportError, match='torch and transformers'):
            build_rules_model(HOSTED_CONFIG)
