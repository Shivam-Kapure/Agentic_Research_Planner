# ResearchPilot — Implementation Plan (Draft v0.3)

**Repository:** https://github.com/Shivam-Kapure/Agentic_Research_Planner
**Hosting:** Render (backend, free) · Vercel (frontend, free) · Supabase (Postgres + Auth, free)

> Status: **Planning.** This is a working draft to iterate on before any code is written.
> Items marked **[DECIDE]** need a team decision. Items marked **[REC]** are my recommendations.

---

## 0. TL;DR — The Key Recommendations

1. **Keep the 5 agents exactly as proposed.** The synopsis is already approved; changing the roster creates a consistency penalty (Section E). We sharpen *how* they coordinate rather than *who* they are.
2. **Orchestration pattern: "Blackboard + agent-directed handoffs, with the Planner as arbiter."** Agents decide their own next step with an LLM call and address requests to each other. No hard-coded `A → B → C` edges. Code enforces only budgets and termination, and every guard that fires is logged. This answers rubric §1.2 directly.
3. **Make adaptation happen for real, from measurable triggers.** Coverage below threshold, contradictions found, PDF unavailable, unsupported claim in the draft. Every one of these produces a real message and a real loop-back. We never script or fake the trace.
4. **The execution trace is a first-class product feature, not a log file.** It is structured JSONL events plus a live trace view in the UI, exportable for submission. This is the strongest evidence for Section A (8 marks).
5. **Stack:** Python 3.11, LangGraph, Pydantic structured outputs, FastAPI with SSE streaming, a React (Vite) UI, and Postgres. Gemini and Groq run behind a provider-failover layer. OpenAlex is the primary source, with Semantic Scholar and Crossref as secondaries.
6. **Engineer for Section G from day 1.** Each member owns a clear slice (see §9), works on feature branches, opens PRs that a teammate reviews, and commits steadily across the build window (see §13).
7. **Authentication + Bring-Your-Own-Key (BYOK).** Users sign in with Supabase Auth. Before their first run, they add their own Groq and Gemini API keys. Keys are validated live, encrypted at rest, and never logged or put in the trace (see §14).

---

## 1. Rubric → Design Mapping

| Rubric item | Marks | How ResearchPilot earns it | Evidence location |
|---|---|---|---|
| A1 Agent count & role clarity | 3 | 5 agents, one package each (`agents/planner/` …), own prompt, own tools, own output schema | Code, design doc, trace `agent` field |
| A2 Genuine agentic behaviour | 3 | Planning (Planner), ReAct tool loops (Search/Analysis), memory (blackboard + paper cache), **adaptation** (query refinement, replans, re-analysis) | Trace events `decision`, `tool_call`, `adaptation` |
| A3 Inter-agent coordination | 2 | Typed messages: `REQUEST`, `CRITIQUE`, `CONFLICT`, `REPLAN_REQUEST`, `APPROVAL`, `REJECTION`; Planner arbitrates | Trace `message` events, UI message graph |
| B1 Architecture diagram | 3 | Mermaid and draw.io diagram: every agent, the blackboard, the message bus, tools, and data direction | Design doc |
| B2 Roles & orchestration pattern | 3 | Named pattern + justification vs. alternatives | Design doc §Orchestration |
| B3 I/O definitions | 2 | JSON Schema generated from Pydantic models, with real samples taken from actual runs | `docs/io/` |
| C1 End-to-end live | 4 | Deployed URL, async runs, live progress | Project URL |
| C2 Robustness | 2 | Input validation, tool fallbacks, LLM failover, partial-result mode | Demo + tests |
| D Presentation | 8 | Each member presents their own agent; we rehearse "why not one agent?" | — |
| E Documentation consistency | 5 | Schemas and diagrams generated from code where possible, so docs can't drift | `docs/`, CI check |
| F Code/engineering | 5 | Clean layout, README, `.env.example`, pytest with a fake LLM, GitHub Actions CI, conventional commits | Repo |
| G Individual | 5 | Ownership matrix, PR-based flow, steady commits | GitHub history |

---

## 2. Architecture

### 2.1 Orchestration pattern [REC]

**Hybrid blackboard with agent-directed routing and Planner arbitration.**

- **Blackboard (shared state):** a LangGraph `State` (Pydantic) holding the plan, the paper pool, evidence records, the synthesis, the draft, the message inbox per agent, budgets, and the trace. The LangGraph checkpointer persists it, which gives memory and resumability.
- **Agent-directed routing:** each agent node ends by returning a LangGraph `Command(goto=<agent>, update=...)`. The target is **chosen by the agent's LLM** from its allowed set, with a stated `reason`. Example: Synthesis can choose `search` (more evidence), `analysis` (deeper re-read), `planner` (replan), or `writer` (sufficient).
- **Planner as arbiter:** when two requests conflict (for example, Synthesis wants more search but the budget is low, or Writer rejects something Synthesis approved), the message goes to the Planner. The Planner decides with an LLM call and logs a `RESOLUTION` event.
- **Deterministic guards (code, not LLM):** max total steps, max replans (2), max search rounds (3), and a per-run token and time budget. When a guard fires, it logs a `GUARD` event and forces the Planner to wrap up. This keeps the system agentic while making the demo safe from runaway loops.

**Why not the alternatives (for the design doc):**
- *Pure sequential pipeline:* this is exactly what rubric §1.2 penalises.
- *Pure peer-to-peer with no arbiter:* it risks deadlocks and ping-pong loops, and it's hard to demo reliably.
- *Central supervisor that decides everything:* it collapses into "one agent with tools". The workers become dumb nodes, which hurts A2.

### 2.2 High-level diagram (draft; final will be Mermaid in the design doc)

```
                         ┌──────────────────────────┐
     User question ───►  │   Research Planner (P)   │◄────── REPLAN_REQUEST / CONFLICT
                         │ decompose · plan · arbit.│
                         └────────────┬─────────────┘
                                      │ plan + REQUEST
                ┌─────────────────────▼─────────────────────┐
                │          BLACKBOARD (shared state)         │
                │ plan · papers · evidence · synthesis ·     │
                │ draft · inboxes · budgets · trace          │
                └──▲──────────▲───────────▲───────────▲──────┘
                   │          │           │           │
        ┌──────────┴──┐ ┌─────┴──────┐ ┌──┴─────────┐ ┌┴────────────┐
        │ Lit. Search │ │ Doc        │ │ Evidence   │ │ Review      │
        │ (S)         │ │ Analysis(A)│ │ Synthesis  │ │ Writer (W)  │
        │ OpenAlex/S2 │ │ PDF/abstr. │ │ (Y)        │ │ draft+verify│
        └──────▲──────┘ └─────▲──────┘ └──┬─────▲───┘ └──┬──────────┘
               │              │           │     │        │
               └── REQUEST ───┴───────────┘     └─CRITIQUE┘
                 (more evidence / re-analyse)   (unsupported claim)
```

### 2.3 Agent specifications

Every agent has the same internal shape: **observe** its inbox and the relevant blackboard slice, **reason or plan** with an LLM producing structured output, **act** through a tool loop, **reflect** with a self-check, and **decide** its next hop with a reason. All of this is traced.

| Agent | Responsibilities | Tools | Adaptive decisions it can make |
|---|---|---|---|
| **Research Planner (P)** | Clarifies the question, picks the domain mode (§2.7), decomposes the question into 3–5 sub-questions, sets inclusion criteria and evidence requirements (min papers per sub-question), presents the plan for user approval (§2.8), arbitrates conflicts, approves termination | `scope_check` (validates the question is a research question), `keyword_extractor`, `field_detector` (OpenAlex topics), budget reader | Replan sub-questions; narrow or broaden scope; switch from keyword mode to domain mode once the dominant field is detected; revise the plan from user feedback; drop an unanswerable sub-question; resolve conflicts; end the run |
| **Literature Search (S)** | Generates queries per sub-question, searches, dedupes, ranks, and scores coverage | `openalex_search`, `semantic_scholar_search`, `crossref_lookup`, `dedupe`, `coverage_score` | Refine or broaden queries; switch source on failure; tell the Planner "literature insufficient for SQ2" |
| **Document Analysis (A)** | Fetches open-access full text (falling back to the abstract) and extracts structured evidence: method, dataset, sample, results, limitations, claim → quote | `resolve_oa_pdf` (OpenAlex `oa_url` / Unpaywall / arXiv), `pdf_extract` (PyMuPDF), `section_chunker` | Choose deep vs. shallow reading; flag low reliability (abstract-only); re-analyse a paper on request with a focused question |
| **Evidence Synthesis (Y)** | Builds the evidence matrix (SQ × paper), clusters agreement, detects contradictions, grades strength, and finds gaps | `evidence_matrix`, `contradiction_check` (LLM pairwise on claims), `strength_grader` | Request more search for a contested claim; request focused re-analysis; request a replan; mark a conflict "unresolved – reported as such" |
| **Review Writer (W)** | Drafts the structured review, verifies that every claim cites evidence IDs, critiques its own draft, and issues the final approval | `citation_verifier` (claim ↔ evidence entailment), `bibliography_formatter` (APA from Crossref metadata) | Reject unsupported claims (CRITIQUE → Y); rewrite or drop claims; approve the final review |

### 2.4 Coordination scenarios we will design for (and demo)

These are **real code paths**, triggered by real data conditions:

1. **Low coverage → query refinement → replan.** S finds fewer than N quality papers for SQ3. It first refines its queries itself. If coverage is still low, it sends `REPLAN_REQUEST` to P, and P broadens or merges the sub-question.
2. **Contradiction → more evidence + deeper analysis.** Y detects Paper 4 vs. Paper 9 disagreeing. It sends `REQUEST(search, "studies on X under condition Y")` and `REQUEST(analysis, "re-read P4 §Results for sample size")`. Then it re-synthesises and grades the conflict as resolved, explained, or open.
3. **Unsupported claim → critique loop.** W's verifier finds a sentence without supporting evidence. It sends `CRITIQUE` to Y. Y supplies the evidence or retracts the claim, and W revises.
4. **Tool failure → fallback.** OpenAlex times out, so S switches to Semantic Scholar and logs it. If a PDF is paywalled, A falls back to the abstract with `reliability="abstract_only"`.
5. **Conflict arbitration.** Y wants a 4th search round but the budget is exhausted. P arbitrates: "proceed and report the gap as a limitation."

### 2.5 Message & trace schema (draft)

```python
class AgentMessage(BaseModel):
    id: str
    run_id: str
    sender: AgentName          # planner|search|analysis|synthesis|writer
    recipient: AgentName
    type: Literal["REQUEST","RESPONSE","CRITIQUE","CONFLICT",
                  "REPLAN_REQUEST","RESOLUTION","APPROVAL","REJECTION"]
    in_reply_to: str | None
    reason: str                # LLM-generated justification
    payload: dict
    ts: datetime

class TraceEvent(BaseModel):
    run_id: str; seq: int; ts: datetime
    agent: AgentName | Literal["system"]
    kind: Literal["thought","decision","tool_call","tool_result",
                  "message","adaptation","guard","error","state_diff"]
    data: dict                 # model, tokens, latency, inputs/outputs (truncated)
```

The trace is stored in Postgres, streamed to the UI over SSE, and exportable as `trace_<run_id>.jsonl` plus a rendered HTML or Markdown for submission.

### 2.6 Memory

- **Working memory:** the blackboard state, persisted by the LangGraph checkpointer (Postgres).
- **Per-agent memory:** each agent keeps a scratchpad of its past decisions in the state, so it does not repeat failed queries.
- **Long-term cache:** a `papers` and `analyses` cache keyed by DOI or OpenAlex ID across runs. It is faster, cheaper, and gives a demonstrable "remembered" behaviour.

### 2.7 Domain handling: general by default, deep when specified (decided)

The system is **domain-general**. How deep it goes depends on whether the user names a domain.

| | **Keyword mode** (no domain given) | **Domain mode** (user sets `domain`, e.g. "clinical medicine") |
|---|---|---|
| Planner | Extracts core concepts, synonyms, and related terms; keeps sub-questions concept-centred | Builds domain-specific sub-questions (e.g. population/intervention/outcome for clinical topics; tasks/benchmarks/baselines for CS) |
| Search | Broad cross-disciplinary keyword queries across OpenAlex/S2, ranked by relevance + citations | Queries filtered by the domain's OpenAlex topics/fields, plus domain vocabulary; more papers per sub-question |
| Analysis | Generic evidence schema (method, data, findings, limitations) | Generic schema **plus domain fields** (e.g. sample size, study design and RCT status for medicine; dataset, metric and SOTA comparison for CS) |
| Synthesis | Agreement/contradiction on concept-level claims | Adds domain-aware evidence grading (e.g. a study-design hierarchy in medicine) |

**Adaptive switch:** in keyword mode, after the first search round, the Planner checks the OpenAlex topic distribution of the results. If one field clearly dominates (for example, more than 60% of the papers), it may **switch to domain mode for that field** and tell the user why. That's a real, traceable adaptation. Domain profiles live in `backend/app/domains/` as small config files (`general`, `cs`, `medicine`, `social_science`, …) so adding one is cheap.

### 2.8 Human-in-the-loop plan approval (decided)

- After the Planner drafts the plan, the graph **pauses** using a LangGraph `interrupt`. The run's state is saved by the checkpointer, so the pause survives a server sleep or restart.
- The UI shows the plan: sub-questions, keywords, domain mode, inclusion criteria, and budget. The user can:
  - **Approve**, and the run continues.
  - **Edit** sub-questions or keywords inline, then approve.
  - **Reject with feedback**, e.g. "focus on studies after 2020, ignore animal studies". The feedback goes to the Planner as a `HUMAN_FEEDBACK` message and it replans. The **revised plan comes back for approval** (max 3 rounds).
- Approval is a per-run toggle that is **on by default** (`require_plan_approval: true`). Turning it off gives a fully autonomous run, which is handy for testing.
- **Mid-run replans** (triggered by agents in §2.4) **don't** pause for approval, so autonomy is preserved. They're shown live in the timeline, and the final output lists every plan revision and why it happened.
- Trace events: `plan_proposed`, `human_feedback`, `plan_revised`, `plan_approved`. All of these are good evidence for rubric A2/A3.

---

## 3. Input / Output Definitions (draft)

**Input**
```json
{
  "question": "Does retrieval-augmented generation reduce hallucination in LLMs compared to fine-tuning?",
  "domain": null,                 // optional, e.g. "computer science"; null → keyword mode (§2.7)
  "keywords": [],                 // optional user-supplied keywords; Planner adds more
  "constraints": {
    "year_from": 2019, "year_to": 2026,
    "max_papers": 15,
    "include_preprints": true
  },
  "depth": "standard",            // quick | standard | deep (controls budgets)
  "require_plan_approval": true   // HITL plan checkpoint (§2.8), default on
}
```

**Output** (abridged)
```json
{
  "run_id": "...",
  "status": "completed | completed_with_limitations | failed",
  "plan": { "domain_mode": "keyword | domain:<name>", "keywords": [...], "sub_questions": [...], "criteria": {...},
            "revisions": [{ "by": "human | planner", "reason": "..." }] },
  "papers": [{ "id": "W123", "doi": "...", "title": "...", "year": 2023, "reliability": "full_text" }],
  "evidence_matrix": [{ "sub_question": "SQ1", "paper_id": "W123", "finding": "...", "quote": "...", "strength": "moderate" }],
  "contradictions": [{ "claim": "...", "papers_for": [...], "papers_against": [...], "status": "explained", "explanation": "..." }],
  "research_gaps": ["..."],
  "review": { "sections": [{ "heading": "...", "paragraphs": [{ "text": "...", "citations": ["W123"] }] }] },
  "bibliography": ["APA strings"],
  "metrics": { "agents_invoked": 5, "messages": 23, "replans": 1, "llm_calls": 41, "duration_s": 212 },
  "trace_url": "/runs/<id>/trace"
}
```

Real samples will be **copied from actual runs**, never hand-written.

---

## 4. Technology Choices [REC]

| Layer | Choice | Justification |
|---|---|---|
| Agent framework | **LangGraph** (Python) | Stateful graphs, `Command`-based dynamic handoffs, checkpointer (memory), interrupts (HITL). Named in the rubric as a legitimate framework. |
| LLMs | **Gemini (Flash-tier)** for Analysis and Writer (long context, cheap); **Groq-hosted open model (Llama/Qwen 70B-class)** for Planner, Search, and routing decisions (fast) | Per-agent model choice is something evaluators ask about (D2). It sits behind a `LLMRouter` with **automatic failover** between providers (Robustness C2). Exact model IDs live in config and are checked against current availability. |
| Structured output | Pydantic v2 + provider JSON mode + 1 repair retry | Reliable inter-agent contracts; the JSON Schemas for the docs are generated from the same models. |
| Literature APIs | OpenAlex (primary, free, has `oa_url`), Semantic Scholar (secondary, citation data), Crossref (metadata/DOI), Unpaywall/arXiv (PDFs) | Redundancy enables fallback behaviour. |
| PDF | PyMuPDF (`pymupdf`) | Fast and robust. Limited to the first ~N pages and key sections. |
| Backend | FastAPI, background tasks, SSE | Long runs (2–5 min) need async jobs plus live progress. |
| DB | **Supabase Postgres** (free tier); SQLite locally | Persistent runs, traces, cache, checkpoints, and encrypted keys. We use Supabase rather than Render Postgres because Render's free DB expires after 30 days. |
| Frontend | **React + Vite + TypeScript + Tailwind** (decided), React Router, TanStack Query, React Flow for the agent message graph | Live agent timeline, message graph, evidence matrix, and final review. |
| Auth | **Supabase Auth** (email/password + Google sign-in); FastAPI verifies the Supabase JWT | Avoids hand-rolling password storage. It shares the Supabase Postgres we already use. |
| Secrets (user keys) | `cryptography` Fernet encryption with a server-side `KEY_ENCRYPTION_SECRET` | User API keys are encrypted at rest and decrypted only in memory for a run. |
| Observability | Own trace store (primary) + optional LangSmith | Our own trace is the submission artifact. LangSmith is a bonus. |
| Deploy | **Backend: Render free web service (Docker). Frontend: Vercel free** (decided) | Constraints and mitigations for the free tiers are in §15. |
| CI | GitHub Actions: ruff, mypy (light), pytest | Section F. |

**Frontend: decided, React (Vite).**

---

## 5. Repository Structure (proposed)

```
researchpilot/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routes: /runs, /runs/{id}, /runs/{id}/stream, /runs/{id}/trace
│   │   ├── agents/
│   │   │   ├── base.py     # BaseAgent: observe→reason→act→reflect→decide, tracing hooks
│   │   │   ├── planner/    # agent.py, prompts.py, schemas.py
│   │   │   ├── search/
│   │   │   ├── analysis/
│   │   │   ├── synthesis/
│   │   │   └── writer/
│   │   ├── graph/          # state.py (blackboard), build_graph.py, guards.py
│   │   ├── messaging/      # AgentMessage, bus helpers
│   │   ├── tools/          # openalex.py, semantic_scholar.py, crossref.py, pdf.py, verifier.py
│   │   ├── llm/            # router.py (Gemini/Groq + failover), structured.py
│   │   ├── tracing/        # TraceEvent, store, exporters (jsonl/html)
│   │   ├── db/             # models, migrations
│   │   └── config.py
│   ├── tests/
│   │   ├── unit/           # tools (respx-mocked HTTP), schemas, guards
│   │   ├── agents/         # each agent with a FakeLLM → asserts decisions/messages
│   │   └── integration/    # full graph with scripted FakeLLM: replan + critique loops occur
│   └── pyproject.toml
├── frontend/               # React app
├── docs/
│   ├── design.md           # architecture, roles, pattern, tech justification
│   ├── synopsis.md
│   ├── io/                 # input.schema.json, output.schema.json, sample_input.json, sample_output.json
│   ├── diagrams/
│   └── traces/             # real exported traces for submission
├── .github/workflows/ci.yml
├── .env.example  .gitignore  docker-compose.yml  README.md
```

---

## 6. Robustness Plan (Live Demo C2)

| Failure | Behaviour |
|---|---|
| Empty, too short, or non-research input | 422 with a clear message. P's `scope_check` can return "too vague", with suggested refinements shown in the UI. |
| Extremely broad question | P narrows the scope and states its assumptions in the plan (traced). |
| Literature API timeout or rate limit (429) | Retry with backoff, then the alternate source, logged as `adaptation`. |
| PDF unavailable or corrupt | Abstract-only analysis, `reliability` lowered, and Synthesis weights it lower. |
| LLM provider error or quota | Failover to the other provider; malformed JSON gets a repair retry. |
| Agent crashes | Error event, the Planner is notified, and the run continues with a partial result → `completed_with_limitations`. |
| Budget exhausted | A guard fires, P wraps up, and the review includes a "Limitations" section. |

---

## 7. Testing Strategy (Section F)

- **FakeLLM** (scripted responses) lets us test agent decisions deterministically. Example: "given contradictory evidence, Synthesis emits a REQUEST to search".
- **Integration test:** a full graph run with a scripted FakeLLM plus mocked APIs. It asserts that at least one replan and one critique loop occur, that it terminates under budget, and that the output validates against the schema.
- **Tool tests:** HTTP is mocked with `respx`, plus a few recorded fixtures of real OpenAlex responses.
- **Smoke test (manual / nightly):** one real run against the live APIs.

---

## 8. Phased Build Plan

No fixed dates. The phases are ordered milestones, and the durations are relative guidance only.

| Phase | Goal | Deliverables | Exit criterion |
|---|---|---|---|
| **0. Setup** (days 1–2) | Repo, CI, skeletons | Repo structure, `.env.example`, CI green, LLM router with both providers, everyone's GitHub registered | Each member has merged ≥1 PR |
| **1. Walking skeleton** (week 1) | End-to-end with simple agents | State/blackboard, message + trace schema, 5 agents with minimal prompts, linear happy path *temporarily*, CLI run | A question produces a (rough) review plus a trace |
| **2. Real tools** (week 2) | Real search, PDF, analysis | OpenAlex/S2/Crossref tools, PDF pipeline, evidence extraction schema, cache | 10–15 real papers analysed with structured evidence |
| **3. Agentic coordination** (week 2–3) | Replace the linear path with agent-directed routing | `Command`-based handoffs, the 5 coordination scenarios (§2.4), Planner arbitration, guards, citation verifier | Integration tests show replan + critique + conflict resolution in real runs |
| **4. API + UI + auth + deploy** (week 3) | Live product | FastAPI + SSE, Supabase Auth, API-key onboarding (§14), React UI (run form, live agent timeline, message graph, evidence matrix, review, trace export), deployed URL | A teammate signs up, adds keys, and runs it from the public URL |
| **5. Hardening + docs** (week 4) | Robustness and artifacts | Failure handling, design doc + diagrams, I/O schemas + real samples, captured traces, README, demo video | All artifacts are cross-consistent; a full rehearsal is done |

Note on Phase 1: the temporary linear path exists only to unblock parallel work. It is fully replaced in Phase 3, and the commit history will show that evolution, which is good evidence of iterative engineering.

---

## 9. Team & Contribution Plan (Section G)

> **Update:** Shivam is the sole developer and authors all code. The table below now defines each teammate's **area for PR review and presentation/Q&A**. Shivam's own code is reviewed by Kashyup. Teammates earn Section G credit mainly through PR reviews, so a large share of their individual 5 marks is at risk.

Team of 4. The original ownership split was agreed as follows. Five agents across four people, so the slices are grouped by how tightly the pieces interact.

| Member | PRN | GitHub | Primary ownership | Secondary | Reviews PRs of |
|---|---|---|---|---|---|
| **Shivam Kapure** | 23070122113 | [@Shivam-Kapure](https://github.com/Shivam-Kapure) | Research Planner agent (incl. domain modes §2.7 + plan approval §2.8), LangGraph graph/orchestration, guards, messaging + trace core, LLM router (per-user keys, failover) | Design document + architecture diagram | Kashyup |
| **Harsh Ledwani** | 23070122100 | [@HARSHHLEDWANI](https://github.com/HARSHHLEDWANI) | Literature Search agent + Document Analysis agent ("evidence acquisition"), OpenAlex/S2/Crossref/PDF tools, domain profiles, paper cache | CI pipeline, tool tests | Shivam |
| **Kashyup Gaud** | 23070122114 | [@kash-gg](https://github.com/kash-gg) | Evidence Synthesis agent + Review Writer agent (the critique loop), contradiction checker, citation verifier, bibliography | I/O schemas + real samples | Kisna |
| **Kisna Kanti** | 23070122116 | [@kkbot122](https://github.com/kkbot122) | React (Vite) frontend (incl. plan-approval screen), Supabase Auth, API-key onboarding (frontend + backend endpoints + encryption), Render/Vercel deployment + keep-warm | README, demo video | Harsh |

Notes:
- Harsh and Kashyup each own two agents. Kisna's slice (auth, BYOK, UI, deployment) is comparable in size. In the Q&A, each person defends their own slice. Shivam explains the overall coordination design.
- The review ring above means everyone also earns "PRs reviewed" credit.
- Register all four GitHub usernames above on the Project Artifacts page before the first commit.

Rules: no direct pushes to `main`; every PR is reviewed by one other member; we use conventional commit messages (`feat(search): add OpenAlex fallback to S2`); each member commits on most working days. Commit and PR attribution must be honest (rubric §5).

---

## 10. Demo-Day Strategy

- Pre-validate **2–3 research questions** that reliably have contested literature. The point is that real contradictions will naturally trigger the loops, not that we script them. Candidates:
  - "Does retrieval-augmented generation reduce hallucination compared to fine-tuning?"
  - "Is intermittent fasting more effective than continuous calorie restriction for weight loss?"
  - "Does remote work affect software developer productivity?"
- Use `depth=quick` for the live demo (~2 min) and show a previously captured `standard` run's trace as well.
- Keep the backend warm and check API quotas the day before.
- Show robustness live: submit a garbage input, and toggle a "simulate OpenAlex outage" debug flag to show the fallback. The flag is a clearly labelled fault-injection feature, which is legitimate as long as we describe it honestly.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Free-tier LLM rate limits during the demo | Two providers with failover, caching, `quick` depth, and small paid credit as a backup |
| Loops never trigger in a run, so the trace looks linear | Evidence thresholds tuned so real gaps get detected; demo questions chosen for contested topics; never fabricate |
| Infinite agent ping-pong | Hard guards plus per-agent decision memory ("already requested X") |
| Docs drift from code | Schemas generated from Pydantic; diagram reviewed in the final week; consistency checklist |
| Long runtimes (>5 min) | Cap papers, parallelise analysis (LangGraph `Send` fan-out), cache |
| Paywalled PDFs | Prefer OA via OpenAlex `oa_url`; abstract fallback is an explicit, traced reliability downgrade |

---

## 12. Open Questions for the Team

**Decided:** 4 members + GitHub usernames · React + Vite · BYOK (Groq + Gemini) · free tier on Render + Vercel (+ Supabase) · general domain with keyword/domain modes · HITL plan approval (on by default) · ownership split agreed.

Also decided: **repo is public** · **no fixed calendar dates**. Stages S0–S7 are sequenced milestones; the "week" labels in §8/§13 are relative guidance only.

**Still open:** none. The plan is ready to move to S0 (repo bootstrap).

---

## 13. GitHub Push Stages

### 13.1 Ground rules (apply at every stage)
- **Branching:** `main` is always deployable and protected (PR + 1 approval + CI green). Work happens on `feat/<area>-<short-desc>`, `fix/...`, `docs/...`, `test/...`.
- **Push your feature branch at the end of every working day**, even if the work isn't finished. Open a **draft PR** early. Rubric G counts *distinct active days*, so daily pushes matter more than big ones.
- **Merge to `main` via PR only**, small and focused, ideally under 400 changed lines.
- **Never push:** `.env`, API keys, `node_modules/`, `__pycache__/`, `.venv/`, local DBs, or PDFs. `.gitignore` and a secret scan (`gitleaks` in CI) go in at Stage 0.
- **Identity:** each member sets `git config user.email` to an email **verified on their GitHub account**. Otherwise commits won't be attributed to their username.

### 13.2 Stages

| # | Stage (when) | Who pushes | What gets pushed / merged | Tag |
|---|---|---|---|---|
| **S0** | **Repo bootstrap** (Day 1) | **Shivam** confirms the repo is **public**, adds @HARSHHLEDWANI, @kash-gg, and @kkbot122 as collaborators, and enables branch protection | `README.md` (stub), `.gitignore`, `.env.example`, folder skeleton (`backend/`, `frontend/`, `docs/`), `IMPLEMENTATION_PLAN.md`, license | — |
| **S1** | **Tooling & CI** (Day 1–2) | Harsh: CI workflow · Kisna: `npm create vite` React-TS scaffold · Shivam: `pyproject.toml`, FastAPI hello-world, LLM router stub · Kashyup: Pydantic schema stubs | Each as **its own PR**, so all 4 members have a merged PR in week 1 | `v0.0.1` |
| **S2** | **Walking skeleton** (end of week 1) | Everyone (own agent / own area) | State + message + trace schema (Shivam), minimal versions of all 5 agents, CLI run end-to-end, blank React pages + routing | `v0.1.0` |
| **S3** | **Real tools** (week 2, continuous) | Harsh (search/PDF tools + cache), Kashyup (evidence schema, contradiction checker), Kisna (Supabase Auth UI + JWT verification), Shivam (graph state + guards) | Small PRs merged as they get finished; tests come with each PR | `v0.2.0` |
| **S4** | **Agentic coordination** (week 2–3) | Shivam (Command routing + arbitration), Harsh/Kashyup (agent-side decision logic and messages), Kisna (API-key onboarding + encryption) | The linear path is replaced. One PR per coordination scenario (§2.4) with its integration test. **Push the first real trace to `docs/traces/`.** | `v0.3.0` |
| **S5** | **Live UI + first deploy** (week 3) | Kisna (UI + deploy config), Shivam (SSE stream endpoint), all (bug fixes) | FastAPI SSE + React live timeline/message graph; Dockerfile, deploy config; the **Project URL goes live** | `v0.4.0` |
| **S6** | **Hardening & docs** (week 4) | Everyone | Robustness fixes (§6), more tests, design doc + diagram (Shivam), I/O schemas + real samples (Kashyup), README + demo video link (Kisna), CI badge (Harsh) | `v0.9.0` |
| **S7** | **Submission freeze** (deadline − 2 days) | Shivam tags; all verify | Final real traces exported, docs cross-checked against the deployed build. **No feature merges after this, only fixes.** | **`v1.0.0`** |

### 13.3 Shivam-specific push checklist
1. S0: create the repo, protect `main`, invite Harsh, Kashyup, and Kisna, and push the skeleton plus this plan.
2. S1: PR `feat(backend): FastAPI app + LLM router skeleton`.
3. S2: PR `feat(graph): blackboard state, AgentMessage & TraceEvent schemas`, then PR `feat(planner): decomposition + plan schema`.
4. S3–S4: PRs for guards, `Command`-based routing, Planner arbitration, and the trace store and exporter.
5. S5: PR `feat(api): SSE run stream`.
6. S6: PR `docs: design document + architecture diagram`.
7. S7: create the `v1.0.0` tag and release notes.

---

## 14. Authentication & User API Keys (BYOK)

### 14.1 User flow
1. **Sign up / sign in** (Supabase Auth: email + password, or Google).
2. **First login → "Connect your AI providers" onboarding screen.** The New Research page is locked until both keys are saved and validated.
3. The user pastes a **Groq API key** and a **Gemini API key**. The backend checks each one with a cheap live call (it lists available models).
   - **Valid:** the key is saved encrypted. The UI only ever shows a masked value like `gsk_••••••••a91F`.
   - **Invalid or no quota:** a clear inline error appears, and the key is not saved.
4. Later, in **Settings → API Keys**, users can replace a key, re-test it, or delete it.

### 14.2 Security design
| Concern | Design |
|---|---|
| Storage | Table `user_api_keys(user_id, provider, ciphertext, last4, validated_at)`, encrypted with Fernet. The master secret lives only in the server's env var. |
| Transport | HTTPS only. The key goes browser → backend once and is **never sent back** to the browser. |
| Use at run time | Decrypted in memory at run start and passed to the LLM router through the run's config. It is **never placed in LangGraph state**, because state is checkpointed to the DB. |
| Logs and trace | A redaction filter scrubs anything key-shaped (`gsk_…`, `AIza…`) from logs, trace events, and error messages. A unit test enforces this. |
| Isolation | Row-level checks: a user can only use, see, or delete their own keys and runs. |
| Failure | If a key is revoked or out of quota mid-run, the router fails over to the other provider (traced as `adaptation`). If both fail, the run ends `completed_with_limitations` with a "check your API keys" message. |

### 14.3 In-app help text: "How to get your API keys"

> Shown as a collapsible help panel on the onboarding screen. Both keys are free to create. Provider dashboards change occasionally, so the button names may differ slightly.

**Groq API key (takes about 2 minutes)**
1. Go to **https://console.groq.com** and sign in (Google, GitHub, or email).
2. In the left menu, click **API Keys**.
3. Click **Create API Key**, give it a name (e.g. `ResearchPilot`), and confirm.
4. **Copy the key immediately.** It starts with `gsk_` and is shown only once.
5. Paste it into the **Groq API Key** field in ResearchPilot and click **Save & Test**.

**Gemini API key (takes about 2 minutes)**
1. Go to **https://aistudio.google.com** and sign in with your Google account.
2. Click **Get API key** (left menu or top-right).
3. Click **Create API key**. If asked, choose or create a Google Cloud project; the default is fine.
4. Copy the key. It starts with `AIza`.
5. Paste it into the **Gemini API Key** field in ResearchPilot and click **Save & Test**.

**Tips shown to users**
- Treat keys like passwords. Don't share them or paste them anywhere else.
- Free tiers have rate limits. If a run reports "quota exceeded", wait a minute or check your usage in the provider's console.
- You can delete your keys from **Settings → API Keys** at any time. You can also revoke them in the Groq or Google console.

### 14.4 Impact on other sections
- **Rubric C (Live Demo):** each user's quota is their own, which removes our shared-quota risk. The team still needs its own demo account with working keys, tested the day before.
- **Robustness demo:** saving an invalid key shows graceful validation. Revoking a key mid-run shows provider failover.
- **Tests:** key validation (HTTP mocked), encrypt/decrypt round-trip, redaction filter, and endpoint auth (401 without a JWT, 403 for another user's run).
- **Design doc:** add an "Auth & key management" box to the architecture diagram. It sits outside the agent system and feeds the LLM router.

---

## 15. Free-Tier Hosting Plan (Render + Vercel + Supabase)

| Service | Free-tier limit that matters | Mitigation |
|---|---|---|
| **Render web service** (FastAPI backend) | **Sleeps after ~15 min idle**, with a ~30–60 s cold start. 512 MB RAM, shared CPU, ephemeral disk, 750 instance-hours/month | A keep-warm ping on `/health` every 10 min from cron-job.org (free), switched on during the evaluation window. **No heavy ML libs** (no torch or sentence-transformers; embeddings, if any, go through the Gemini API). Process PDFs as a stream and cap pages so they fit in 512 MB. Store nothing on local disk. |
| **Render: long runs** | A restart or redeploy kills in-process background tasks | Runs execute as in-process async tasks. The LangGraph Postgres checkpointer saves state at every step, so an interrupted run can be **resumed** (`POST /runs/{id}/resume`). Max 1–2 concurrent runs per instance, with a queue beyond that. |
| **Vercel** (React SPA) | Static hosting only; fine for our needs | `vercel.json` rewrite for SPA routing. `VITE_API_URL` points to Render. Show a "waking up the server…" state if `/health` is slow. |
| **Supabase** (Postgres + Auth) | **The project pauses after ~7 days of inactivity**; 500 MB DB | The keep-warm ping also touches the DB. Trim stored PDFs: store extracted evidence, not raw files. Truncate large trace payloads. |
| **CORS / SSE** | Cross-origin streaming from Vercel to Render | CORS allowlist = Vercel domain only. SSE with heartbeat comments every 15 s so proxies keep the stream open. |
| **Secrets** | — | Render env vars: `DATABASE_URL`, `SUPABASE_JWT_SECRET`, `KEY_ENCRYPTION_SECRET`. Vercel env vars: `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (public by design). Nothing secret in the repo. |

**Demo-day checklist:** turn the keep-warm ping on 24 h before the demo · open the app 10 min before the slot · run one quick test question · make sure the team demo account's keys have quota · have the demo video and an exported trace ready as backup.
