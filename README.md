# ResearchPilot

**A coordinated multi-agent AI system for adaptive academic literature review.**

ResearchPilot takes a research question and has five specialised AI agents plan, search, analyse, synthesise and write a structured literature review. The agents communicate through a shared blackboard and typed messages. They critique each other's work, resolve conflicting evidence, and replan when the evidence is insufficient. Every decision, message, tool call and adaptation is recorded in an execution trace.

> **Status:** 🚧 Stage S0: repository bootstrap. See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) for the full plan and build stages.

## Agents

| Agent | Role |
|---|---|
| **Research Planner** | Decomposes the question, chooses keyword or domain mode, proposes the plan for user approval, arbitrates conflicts, approves termination |
| **Literature Search** | Queries OpenAlex / Semantic Scholar / Crossref, refines queries, scores coverage, requests replanning |
| **Document Analysis** | Retrieves open-access PDFs (or abstracts) and extracts structured, reliability-rated evidence |
| **Evidence Synthesis** | Builds the evidence matrix, detects contradictions and gaps, requests more search or re-analysis |
| **Review Writer** | Drafts the review, verifies every claim against evidence, critiques and requests revisions |

## Tech stack

LangGraph · FastAPI · Pydantic · Groq + Gemini (bring your own keys) · OpenAlex / Semantic Scholar / Crossref · PyMuPDF · React + Vite + TypeScript · Supabase (Auth + Postgres) · Render + Vercel

## Repository layout

```
backend/    FastAPI app, agents, LangGraph orchestration, tools, tests
frontend/   React (Vite) web app
docs/       Plan, design document, I/O schemas + samples, diagrams, execution traces
```

## Team

Development is led by Shivam Kapure. Each teammate reviews the PRs for one area and presents it.

| Member | GitHub | Area (review & presentation) |
|---|---|---|
| Shivam Kapure | [@Shivam-Kapure](https://github.com/Shivam-Kapure) | Lead developer; Research Planner, orchestration, messaging & trace, LLM router |
| Harsh Ledwani | [@HARSHHLEDWANI](https://github.com/HARSHHLEDWANI) | Literature Search, Document Analysis, academic/PDF tools, CI |
| Kashyup Gaud | [@kash-gg](https://github.com/kash-gg) | Evidence Synthesis, Review Writer, citation verification |
| Kisna Kanti | [@kkbot122](https://github.com/kkbot122) | Frontend, auth, API-key management, deployment |

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). In short: feature branches, PRs reviewed by one teammate, conventional commits, never commit secrets.

## License

[MIT](LICENSE)
