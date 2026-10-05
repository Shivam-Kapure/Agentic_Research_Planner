"""BaseAgent: the observe → reason → act → decide shape shared by all five agents.

Every reasoning step, tool call and message goes through these helpers, so it is traced
automatically, and an agent failure degrades the run instead of crashing it.
"""

import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel

from app.domain.research import AgentName
from app.graph.context import RunContext
from app.graph.state import ResearchState
from app.llm.redaction import redact
from app.messaging import AgentMessage, MessageType

StateUpdate = dict[str, Any]


class BaseAgent(ABC):
    name: AgentName
    system_prompt: str

    async def __call__(self, state: ResearchState, runtime: Runtime[RunContext]) -> StateUpdate:
        """LangGraph node entry point."""
        ctx = runtime.context
        ctx.recorder.record(
            self.name, "agent_started", f"{self.name} started", step=state.steps + 1
        )
        try:
            update = await self.act(state, ctx)
        except Exception as exc:  # degrade gracefully: record, report, continue
            message = redact(f"{type(exc).__name__}: {exc}")[:300]
            ctx.recorder.record(self.name, "error", f"{self.name} failed: {message}")
            update = {"limitations": [f"{self.name} agent failed: {message}"]}
        update["steps"] = state.steps + 1
        ctx.recorder.record(self.name, "agent_finished", f"{self.name} finished")
        return update

    @abstractmethod
    async def act(self, state: ResearchState, ctx: RunContext) -> StateUpdate: ...

    # ------------------------------------------------------------------ helpers

    async def think[T: BaseModel](
        self, ctx: RunContext, schema: type[T], prompt: str, *, summary: str | None = None
    ) -> T:
        """One structured LLM reasoning step using this agent's model profile."""
        result = await ctx.router.structured(
            self.name,
            [SystemMessage(content=self.system_prompt), HumanMessage(content=prompt)],
            schema,
        )
        ctx.recorder.record(
            self.name,
            "thought",
            summary or f"Reasoned with {result.provider}/{result.model} → {schema.__name__}",
            output=result.value,
            provider=result.provider,
            model=result.model,
        )
        return result.value

    async def use_tool[R](
        self,
        ctx: RunContext,
        tool: str,
        call: Callable[[], Awaitable[R]],
        *,
        args: dict[str, Any] | None = None,
        describe: Callable[[R], str] | None = None,
    ) -> R:
        ctx.recorder.record(self.name, "tool_call", f"{tool}({_short(args)})", tool=tool, args=args)
        started = time.perf_counter()
        try:
            result = await call()
        except Exception as exc:
            ctx.recorder.record(
                self.name,
                "error",
                f"{tool} failed: {type(exc).__name__}",
                tool=tool,
                error=str(exc),
                latency_ms=_ms(started),
            )
            raise
        ctx.recorder.record(
            self.name,
            "tool_result",
            describe(result) if describe else f"{tool} returned",
            tool=tool,
            latency_ms=_ms(started),
        )
        return result

    def decide(self, ctx: RunContext, summary: str, **data: Any) -> None:
        ctx.recorder.record(self.name, "decision", summary, **data)

    def adapt(self, ctx: RunContext, summary: str, **data: Any) -> None:
        ctx.recorder.record(self.name, "adaptation", summary, **data)

    def send(
        self,
        ctx: RunContext,
        to: AgentName,
        type: MessageType,
        reason: str,
        payload: dict[str, Any] | None = None,
        in_reply_to: str | None = None,
    ) -> AgentMessage:
        message = AgentMessage(
            sender=self.name,
            recipient=to,
            type=type,
            reason=reason,
            payload=payload or {},
            in_reply_to=in_reply_to,
        )
        ctx.recorder.record(
            self.name,
            "message",
            f"{self.name} → {to} [{type}] {reason}",
            message=message,
        )
        return message


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _short(args: dict[str, Any] | None) -> str:
    if not args:
        return ""
    text = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return text if len(text) <= 120 else text[:117] + "..."
