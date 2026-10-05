import { Link } from 'react-router'

const agents = [
  ['Research Planner', 'Decomposes your question, proposes a plan for your approval, and arbitrates conflicts.'],
  ['Literature Search', 'Searches OpenAlex, Semantic Scholar and Crossref, and refines queries when coverage is thin.'],
  ['Document Analysis', 'Reads open-access papers and extracts structured, reliability-rated evidence.'],
  ['Evidence Synthesis', 'Compares studies, detects contradictions and gaps, and requests more evidence.'],
  ['Review Writer', 'Writes the review and rejects any claim that lacks supporting evidence.'],
] as const

export function HomePage() {
  return (
    <section className="space-y-8">
      <div className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          Adaptive literature reviews by a team of AI agents
        </h1>
        <p className="max-w-2xl text-slate-600">
          Five specialised agents plan, search, analyse, synthesise and write — critiquing each
          other and replanning when the evidence is thin or contradictory. Every decision is
          recorded in a transparent execution trace.
        </p>
        <Link
          to="/research/new"
          className="inline-block rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          Start a review
        </Link>
      </div>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map(([name, description]) => (
          <li key={name} className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="font-medium">{name}</h2>
            <p className="mt-1 text-sm text-slate-600">{description}</p>
          </li>
        ))}
      </ul>
    </section>
  )
}
