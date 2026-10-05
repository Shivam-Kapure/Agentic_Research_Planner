# Frontend

React + Vite + TypeScript + Tailwind web app for ResearchPilot. It is deployed on Vercel.

## Setup

```bash
cd frontend
npm install
```

`VITE_*` variables are read from the repo-root `.env` (see `../.env.example`). In development, `VITE_API_URL` defaults to `http://localhost:8000`.

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Dev server at http://localhost:5173 |
| `npm run build` | Type-check + production build into `dist/` |
| `npm test` | Run component tests (Vitest + Testing Library) |
| `npm run lint` | Lint with Oxlint |

## Deployment (Vercel)

Root directory: `frontend`. Set the env vars `VITE_API_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY`. `vercel.json` rewrites all routes to `index.html` for client-side routing.
