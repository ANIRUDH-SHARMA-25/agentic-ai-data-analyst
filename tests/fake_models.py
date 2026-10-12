"""Shared deterministic model; never connects to a provider."""
from evaluations.fake_model import ScriptedModel, call_tool

__all__ = ["ScriptedModel", "call_tool"]
