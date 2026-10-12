"""A tool-calling chat model that never opens a network connection."""

from typing import Any
from uuid import uuid4

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedModel(BaseChatModel):
    responses: list[Any]
    index: int = 0
    bound_names: list[str] = Field(default_factory=list)
    observed_messages: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "network-free-scripted-tools"

    def bind_tools(self, tools, **kwargs):
        self.bound_names = [tool.name for tool in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.observed_messages = messages
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response(messages)
        return ChatResult(generations=[ChatGeneration(message=response)])


def call_tool(name, arguments=None):
    return AIMessage(content="", tool_calls=[{
        "name": name, "args": arguments or {}, "id": uuid4().hex, "type": "tool_call",
    }])
