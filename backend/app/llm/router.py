"""LLM router: per-agent model selection, structured output with one repair retry,
and automatic failover between providers.

Every attempt is reported through `on_event` so the tracing layer can record model usage
and failovers as adaptation events in the execution trace.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel

from app.llm.profiles import DEFAULT_PROFILES, AgentRole
from app.llm.providers import LLMCredentials, ModelFactory, ModelSpec, build_chat_model
from app.llm.redaction import redact

LLMEvent = dict[str, Any]


class NoProviderAvailableError(RuntimeError):
    """No configured provider could serve the request."""


class AllProvidersFailedError(RuntimeError):
    """Every model in the agent's profile failed."""

    def __init__(self, role: str, attempts: list["Attempt"]):
        summary = "; ".join(f"{a.provider}/{a.model}: {a.error}" for a in attempts)
        super().__init__(f"All providers failed for '{role}': {summary}")
        self.attempts = attempts


@dataclass
class Attempt:
    provider: str
    model: str
    ok: bool
    latency_ms: int
    error: str | None = None
    repaired: bool = False


@dataclass
class LLMResult[R]:
    value: R
    provider: str
    model: str
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def failed_over(self) -> bool:
        return len(self.attempts) > 1


class LLMRouter:
    def __init__(
        self,
        credentials: LLMCredentials,
        profiles: dict[AgentRole, list[ModelSpec]] | None = None,
        model_factory: ModelFactory = build_chat_model,
        on_event: Callable[[LLMEvent], None] | None = None,
    ):
        self._credentials = credentials
        self._profiles = profiles or DEFAULT_PROFILES
        self._factory = model_factory
        self._on_event = on_event or (lambda _event: None)

    def _candidates(self, role: AgentRole) -> list[ModelSpec]:
        if role not in self._profiles:
            raise KeyError(f"No model profile for agent role '{role}'")
        candidates = [s for s in self._profiles[role] if self._credentials.key_for(s.provider)]
        if not candidates:
            raise NoProviderAvailableError(
                f"No API key configured for any provider usable by '{role}'"
            )
        return candidates

    async def structured[T: BaseModel](
        self, role: AgentRole, messages: Sequence[BaseMessage], schema: type[T]
    ) -> LLMResult[T]:
        """Call the agent's model and parse the reply into `schema`.

        On a parse/validation failure the same model gets one repair attempt; on any other
        failure (or a failed repair) the router moves to the next model in the profile.
        """

        async def call(spec: ModelSpec) -> tuple[T, bool]:
            model = self._factory(spec, self._credentials.key_for(spec.provider))
            runnable = model.with_structured_output(schema)
            try:
                return _coerce(await runnable.ainvoke(list(messages)), schema), False
            except Exception as first_error:  # parse/validation errors â†’ one repair retry
                if not _is_parse_error(first_error):
                    raise
                repair = HumanMessage(
                    content=(
                        "Your previous reply did not match the required JSON schema "
                        f"({redact(str(first_error))[:300]}). Reply again with valid output only."
                    )
                )
                return _coerce(await runnable.ainvoke([*messages, repair]), schema), True

        return await self._run(role, call)

    async def text(self, role: AgentRole, messages: Sequence[BaseMessage]) -> LLMResult[str]:
        async def call(spec: ModelSpec) -> tuple[str, bool]:
            model = self._factory(spec, self._credentials.key_for(spec.provider))
            reply = await model.ainvoke(list(messages))
            return str(reply.content), False

        return await self._run(role, call)

    async def _run(self, role: AgentRole, call) -> LLMResult:
        attempts: list[Attempt] = []
        for spec in self._candidates(role):
            started = time.perf_counter()
            try:
                value, repaired = await call(spec)
            except Exception as exc:
                attempt = Attempt(
                    spec.provider,
                    spec.model,
                    ok=False,
                    latency_ms=_elapsed_ms(started),
                    error=redact(f"{type(exc).__name__}: {exc}")[:500],
                )
                attempts.append(attempt)
                self._emit(role, attempt, kind="llm_failure")
                continue
            attempt = Attempt(
                spec.provider,
                spec.model,
                ok=True,
                latency_ms=_elapsed_ms(started),
                repaired=repaired,
            )
            attempts.append(attempt)
            if len(attempts) > 1:
                self._emit(role, attempt, kind="llm_failover", previous=attempts[:-1])
            self._emit(role, attempt, kind="llm_call")
            return LLMResult(value, spec.provider, spec.model, attempts)
        raise AllProvidersFailedError(role, attempts)

    def _emit(self, role: str, attempt: Attempt, kind: str, previous=None) -> None:
        event: LLMEvent = {
            "kind": kind,
            "agent": role,
            "provider": attempt.provider,
            "model": attempt.model,
            "latency_ms": attempt.latency_ms,
            "ok": attempt.ok,
            "repaired": attempt.repaired,
            "error": attempt.error,
        }
        if previous:
            event["failed_over_from"] = [f"{a.provider}/{a.model}" for a in previous]
        self._on_event(event)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _coerce[T: BaseModel](raw: Any, schema: type[T]) -> T:
    if isinstance(raw, schema):
        return raw
    if raw is None:
        raise ValueError("Model returned no structured output")
    return schema.model_validate(raw)


def _is_parse_error(exc: Exception) -> bool:
    from langchain_core.exceptions import OutputParserException
    from pydantic import ValidationError

    return isinstance(exc, OutputParserException | ValidationError | ValueError)
