"""Test doubles: a fake chat model that answers according to the requested output schema."""

from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage

Responder = Callable[[type, list], Any]


class SchemaFakeModel:
    """Stands in for a LangChain chat model. `responder(schema, messages)` produces the reply
    (a schema instance, a dict, or an Exception to raise)."""

    def __init__(self, responder: Responder):
        self.responder = responder
        self.calls: list[tuple[type | None, list]] = []

    def _reply(self, schema, messages):
        self.calls.append((schema, messages))
        reply = self.responder(schema, messages)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def with_structured_output(self, schema):
        model = self

        class Runnable:
            async def ainvoke(self, messages):
                return model._reply(schema, messages)

        return Runnable()

    async def ainvoke(self, messages):
        return AIMessage(content=str(self._reply(None, messages)))


def factory_for(models: dict[str, SchemaFakeModel]):
    """Model factory for LLMRouter: picks the fake by provider name."""

    def factory(spec, api_key):
        return models[spec.provider]

    return factory
