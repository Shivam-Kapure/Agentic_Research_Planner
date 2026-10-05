"""Provider identities, per-user credentials and chat-model construction."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

Provider = Literal["groq", "gemini"]


@dataclass(frozen=True)
class LLMCredentials:
    """A user's own (BYOK) provider keys, decrypted only for the lifetime of a run.

    Never stored in graph state or traces: SecretStr keeps them out of repr/logs.
    """

    groq_api_key: SecretStr | None = field(default=None, repr=False)
    gemini_api_key: SecretStr | None = field(default=None, repr=False)

    def key_for(self, provider: Provider) -> SecretStr | None:
        key = self.groq_api_key if provider == "groq" else self.gemini_api_key
        return key if key and key.get_secret_value() else None

    @property
    def available_providers(self) -> list[Provider]:
        return [p for p in ("groq", "gemini") if self.key_for(p)]


@dataclass(frozen=True)
class ModelSpec:
    provider: Provider
    model: str
    temperature: float = 0.2


class ModelFactory(Protocol):
    def __call__(self, spec: ModelSpec, api_key: SecretStr) -> BaseChatModel: ...


def build_chat_model(spec: ModelSpec, api_key: SecretStr) -> BaseChatModel:
    """Default factory creating real provider clients."""
    if spec.provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=spec.model,
            api_key=api_key,
            temperature=spec.temperature,
            max_retries=2,
            timeout=60,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=spec.model,
        google_api_key=api_key,
        temperature=spec.temperature,
        max_retries=2,
        timeout=90,
    )
