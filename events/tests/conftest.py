"""Shared test setup.

torch and transformers are commented out of requirements.txt because only the
locally-hosted model needs them -- the deployed service uses the Gemini API. That
left the hosted model's tests unimportable anywhere the heavy deps aren't
installed, and a collection error in one module takes down the whole run.

Stub the two modules when they are genuinely absent so the hosted model's own
logic (prompt assembly, verdict parsing) stays testable without a GPU stack. When
the real packages are installed these stubs are never used.
"""
import sys
import types
from unittest.mock import MagicMock


def _stub_module(name: str, **attributes) -> None:
    try:
        __import__(name)
    except ImportError:
        module = types.ModuleType(name)
        for attribute, value in attributes.items():
            setattr(module, attribute, value)
        sys.modules[name] = module


_stub_module("torch", bfloat16="bfloat16")
_stub_module(
    "transformers",
    AutoProcessor=MagicMock(name="AutoProcessor"),
    AutoModelForCausalLM=MagicMock(name="AutoModelForCausalLM"),
)
