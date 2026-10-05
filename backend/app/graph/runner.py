"""Runs one literature review end to end and assembles the output."""

import time
from dataclasses import dataclass
from uuid import uuid4

from app.config import Settings
from app.domain.output import ResearchOutput, RunMetrics, RunStatus, format_reference
from app.domain.research import ResearchRequest
from app.graph.build import build_graph
from app.graph.context import RunContext
from app.graph.state import ResearchState, budget_for
from app.llm import LLMCredentials, LLMRouter
from app.llm.providers import ModelFactory, build_chat_model
from app.tools.openalex import OpenAlexClient
from app.tracing import TraceEvent, TraceRecorder, TraceSink


@dataclass
class RunOutcome:
    output: ResearchOutput
    events: list[TraceEvent]


async def run_research(
    request: ResearchRequest,
    credentials: LLMCredentials,
    settings: Settings,
    *,
    run_id: str | None = None,
    sinks: list[TraceSink] | None = None,
    model_factory: ModelFactory = build_chat_model,
    openalex: OpenAlexClient | None = None,
) -> RunOutcome:
    run_id = run_id or f"run_{uuid4().hex[:12]}"
    recorder = TraceRecorder(run_id, sinks)
    router = LLMRouter(credentials, model_factory=model_factory, on_event=recorder.llm_event_sink)
    own_client = openalex is None
    openalex = openalex or OpenAlexClient(
        mailto=settings.openalex_mailto, api_key=settings.openalex_api_key
    )
    ctx = RunContext(run_id=run_id, router=router, recorder=recorder, openalex=openalex)
    initial = ResearchState(run_id=run_id, request=request, budget=budget_for(request))

    recorder.record(
        "system",
        "run_started",
        f"Run started: {request.question}",
        request=request,
        budget=initial.budget,
        providers=credentials.available_providers,
    )
    started = time.perf_counter()
    try:
        result = await build_graph().ainvoke(initial, context=ctx)
        state = ResearchState.model_validate(result)
    except Exception as exc:
        recorder.record("system", "error", f"Run aborted: {type(exc).__name__}: {exc}")
        state = initial.model_copy(update={"limitations": [f"Run aborted: {type(exc).__name__}"]})
    finally:
        if own_client:
            await openalex.aclose()

    status = final_status(state)
    duration = round(time.perf_counter() - started, 2)
    recorder.record("system", "run_finished", f"Run finished with status '{status}' in {duration}s")
    output = ResearchOutput(
        run_id=run_id,
        status=status,
        request=request,
        plan=state.plan,
        papers=state.papers,
        evidence=state.evidence,
        synthesis=state.synthesis,
        review=state.draft,
        bibliography=[format_reference(p) for p in state.papers],
        limitations=list(dict.fromkeys(state.limitations)),
        metrics=_metrics(recorder, state, duration),
    )
    return RunOutcome(output=output, events=list(recorder.events))


def final_status(state: ResearchState) -> RunStatus:
    if state.draft is None:
        return "failed"
    if state.limitations or not state.draft.approved:
        return "completed_with_limitations"
    return "completed"


def _metrics(recorder: TraceRecorder, state: ResearchState, duration: float) -> RunMetrics:
    count = lambda kind: len(recorder.of_kind(kind))  # noqa: E731
    return RunMetrics(
        agents_invoked=len({e.agent for e in recorder.of_kind("agent_started")}),
        agent_steps=state.steps,
        messages=count("message"),
        adaptations=count("adaptation"),
        tool_calls=count("tool_call"),
        llm_calls=count("llm_call"),
        errors=count("error"),
        search_rounds=state.search_rounds,
        replans=state.replans,
        duration_s=duration,
    )
