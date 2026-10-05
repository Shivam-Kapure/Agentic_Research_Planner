from app.messaging import AgentMessage, inbox
from app.tracing import TraceRecorder
from app.tracing.exporters import to_jsonl, to_markdown
from app.tracing.recorder import MAX_VALUE_CHARS

FAKE_KEY = "gsk_" + "Q" * 24


def test_recorder_numbers_events_and_notifies_sinks():
    seen = []
    recorder = TraceRecorder("run_1", sinks=[seen.append])

    recorder.record("planner", "decision", "Decomposed into 3 sub-questions")
    recorder.record("search", "tool_call", "openalex_search(query='rag')")

    assert [e.seq for e in recorder.events] == [1, 2]
    assert seen == recorder.events


def test_recorder_redacts_secrets_and_truncates_large_values():
    recorder = TraceRecorder("run_1")

    event = recorder.record(
        "writer", "error", f"bad key {FAKE_KEY}", detail=f"key={FAKE_KEY}", blob="x" * 5000
    )

    dumped = event.model_dump_json()
    assert FAKE_KEY not in dumped
    assert len(event.data["blob"]) < MAX_VALUE_CHARS + 20


def test_llm_failover_events_become_adaptations():
    recorder = TraceRecorder("run_1")

    recorder.llm_event_sink(
        {
            "kind": "llm_failover",
            "agent": "planner",
            "provider": "gemini",
            "model": "g",
            "failed_over_from": ["groq/x"],
        }
    )

    [event] = recorder.of_kind("adaptation")
    assert event.agent == "planner"
    assert "groq/x" in event.summary


def test_exporters_produce_jsonl_lines_and_markdown_summary():
    recorder = TraceRecorder("run_7")
    recorder.record("planner", "message", "planner → search [REQUEST] find papers")
    recorder.record("search", "adaptation", "Broadened query | after 0 results")

    jsonl = to_jsonl(recorder.events)
    markdown = to_markdown(recorder.events)

    assert len(jsonl.strip().splitlines()) == 2
    assert "run `run_7`" in markdown
    assert "Messages: **1**" in markdown
    assert "Broadened query \\| after 0 results" in markdown


def test_inbox_returns_unhandled_messages_for_recipient():
    to_search = AgentMessage(sender="planner", recipient="search", type="REQUEST", reason="go")
    handled = AgentMessage(sender="planner", recipient="search", type="REQUEST", reason="old")
    to_writer = AgentMessage(sender="synthesis", recipient="writer", type="REQUEST", reason="w")

    pending = inbox([to_search, handled, to_writer], "search", handled={handled.id})

    assert pending == [to_search]
