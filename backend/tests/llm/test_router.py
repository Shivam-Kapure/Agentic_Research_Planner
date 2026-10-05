import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, SecretStr, ValidationError

from app.llm import (
    AllProvidersFailedError,
    LLMCredentials,
    LLMRouter,
    ModelSpec,
    NoProviderAvailableError,
)

GROQ = ModelSpec("groq", "groq-model")
GEMINI = ModelSpec("gemini", "gemini-model")
PROFILES = {"planner": [GROQ, GEMINI]}
FAKE_GROQ_KEY = "gsk_" + "a1b2c3d4e5f6g7h8i9j0"
BOTH_KEYS = LLMCredentials(SecretStr(FAKE_GROQ_KEY), SecretStr("AIza" + "x" * 35))


class Plan(BaseModel):
    sub_questions: list[str]


class FakeModel:
    """Scripted stand-in for a chat model: each call pops the next response.

    A response that is an Exception is raised instead of returned.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[list] = []

    def _next(self, messages):
        self.calls.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def with_structured_output(self, schema):
        fake = self

        class Runnable:
            async def ainvoke(self, messages):
                return fake._next(messages)

        return Runnable()

    async def ainvoke(self, messages):
        return self._next(messages)


def make_router(scripts: dict[str, list], credentials=BOTH_KEYS):
    models = {provider: FakeModel(responses) for provider, responses in scripts.items()}
    events: list[dict] = []

    def factory(spec, api_key):
        return models[spec.provider]

    router = LLMRouter(credentials, PROFILES, model_factory=factory, on_event=events.append)
    return router, models, events


MESSAGES = [HumanMessage(content="Plan a review on RAG vs fine-tuning")]


async def test_primary_provider_success_uses_no_failover():
    router, _, events = make_router({"groq": [Plan(sub_questions=["SQ1"])], "gemini": []})

    result = await router.structured("planner", MESSAGES, Plan)

    assert result.value.sub_questions == ["SQ1"]
    assert (result.provider, result.model) == ("groq", "groq-model")
    assert not result.failed_over
    assert [e["kind"] for e in events] == ["llm_call"]


async def test_fails_over_to_next_provider_on_error():
    router, _, events = make_router(
        {
            "groq": [RuntimeError("429 rate limit exceeded")],
            "gemini": [{"sub_questions": ["SQ1", "SQ2"]}],
        }
    )

    result = await router.structured("planner", MESSAGES, Plan)

    assert result.provider == "gemini"
    assert result.failed_over
    assert result.value.sub_questions == ["SQ1", "SQ2"]
    kinds = [e["kind"] for e in events]
    assert kinds == ["llm_failure", "llm_failover", "llm_call"]
    assert events[1]["failed_over_from"] == ["groq/groq-model"]


async def test_invalid_output_gets_one_repair_retry_on_same_provider():
    bad = ValidationError.from_exception_data("Plan", [])
    router, models, _ = make_router({"groq": [bad, {"sub_questions": ["SQ1"]}], "gemini": []})

    result = await router.structured("planner", MESSAGES, Plan)

    assert result.provider == "groq"
    assert result.attempts[-1].repaired
    repair_prompt = models["groq"].calls[1][-1].content
    assert "did not match the required JSON schema" in repair_prompt


async def test_all_providers_failing_raises_with_redacted_errors():
    router, _, _ = make_router(
        {
            "groq": [RuntimeError(f"401 invalid api_key={FAKE_GROQ_KEY}")],
            "gemini": [RuntimeError("503 unavailable")],
        }
    )

    with pytest.raises(AllProvidersFailedError) as excinfo:
        await router.structured("planner", MESSAGES, Plan)

    assert FAKE_GROQ_KEY not in str(excinfo.value)
    assert len(excinfo.value.attempts) == 2


async def test_providers_without_keys_are_skipped():
    only_gemini = LLMCredentials(gemini_api_key=SecretStr("AIza" + "y" * 35))
    router, models, _ = make_router(
        {"groq": [], "gemini": [{"sub_questions": ["SQ1"]}]}, credentials=only_gemini
    )

    result = await router.structured("planner", MESSAGES, Plan)

    assert result.provider == "gemini"
    assert not result.failed_over
    assert models["groq"].calls == []


async def test_no_keys_raises_no_provider_available():
    router, _, _ = make_router({"groq": [], "gemini": []}, credentials=LLMCredentials())

    with pytest.raises(NoProviderAvailableError):
        await router.structured("planner", MESSAGES, Plan)


async def test_text_call_returns_content():
    router, _, _ = make_router({"groq": [AIMessage(content="hello")], "gemini": []})

    result = await router.text("planner", MESSAGES)

    assert result.value == "hello"


def test_credentials_repr_does_not_leak_keys():
    assert FAKE_GROQ_KEY not in repr(BOTH_KEYS)
    assert BOTH_KEYS.available_providers == ["groq", "gemini"]
