# Frontend — AI Coding Instructions

## Overview
React 18 + TypeScript SPA built with Vite.  Uses Tailwind CSS for styling.

## Structure
```
frontend/
  index.html              — entry HTML, loads /src/main.tsx
  vite.config.ts          — dev server proxies /api → localhost:8000
  vitest.integration.config.ts — separate vitest config for Prism integration tests
  tailwind.config.ts      — brand color palette
  .env.mock               — env vars for mock mode (VITE_API_BASE_URL)
  src/
    main.tsx              — React root, BrowserRouter
    App.tsx               — Route definitions, onboarding gate
    index.css             — Tailwind directives
    vite-env.d.ts         — TypeScript types for VITE_ env vars
    api/client.ts         — Typed fetch wrapper for all /api/v1 endpoints
    api/client.integration.test.ts — Contract tests against Prism mock server
    components/
      Layout.tsx          — Shell: sidebar nav + <Outlet/>
      FeedbackControls.tsx — Thumbs up/down + feedforward note
      SpeechInput.tsx     — Web Speech API dictation button
    pages/
      JournalPage.tsx     — CRUD journal entries with voice input
      ProfilePage.tsx     — Knowledge Profile viewer (topic cards by category)
      QuizPage.tsx        — Active quiz with answer + evaluation display
      ReadingsPage.tsx    — Reading recommendations + allowlist manager
      ProjectsPage.tsx    — Current project + task list + submission
      TriagePage.tsx      — Pending/resolved triage items with resolution UI
      SettingsPage.tsx    — Info page (config via .env)
      OnboardingPage.tsx  — 3-step first-run wizard
    test/
      setup.ts            — jest-dom matchers, jsdom stubs
      helpers.tsx          — renderWithRouter test helper
      prism-global-setup.ts — auto-starts/stops Prism for integration tests
```

## Key conventions
- **API client** (`api/client.ts`): typed wrapper using `fetch()`, all endpoints return typed interfaces. Base URL configurable via `VITE_API_BASE_URL` env var (defaults to `/api/v1` for Vite proxy mode).
- **Generated types are the contract**: `api/schema.gen.ts` is produced from `docs/openapi.json` by `npm run openapi:types` (also run by `make openapi`). Every request/response type in `client.ts` MUST come from `components["schemas"]` in that file. Hand-rolled inline types are how client↔spec drift happens. An architecture test enforces this.
- **Tailwind**: custom `brand-*` color palette. No CSS-in-JS.
- **No state library**: simple `useState`/`useEffect` — app is single-user, low complexity.
- **Feedback on everything**: `FeedbackControls` component is attached to quiz questions, readings, projects.
- **Speech input**: Browser-native Web Speech API, text only — no audio files ever.
- **Onboarding gate**: `App.tsx` checks onboarding status on mount; if incomplete, routes to `/onboarding`.

## Running
```bash
cd frontend
npm install
npm run dev        # dev server at :5173, proxies /api to :8000
npm run dev:mock   # dev server at :5173, hits Prism mock at :4010
npm run build      # outputs to dist/ for production
```

## Mock API (Prism)
The project uses [Stoplight Prism](https://github.com/stoplightio/prism) as a mock API server driven by the OpenAPI spec (`docs/openapi.json`) — the single source of truth for the API contract.

```bash
# Start Prism standalone (port 4010, dynamic responses)
npm run mock-api

# Start Prism + Vite together (from project root)
make dev-mock

# Run integration tests (auto-starts/stops Prism)
npm run test:integration
# or from project root:
make test-integration
```

### How it works
- `docs/openapi.json` is generated from the FastAPI backend (`make openapi`)
- `make openapi` also regenerates `src/api/schema.gen.ts` so `tsc` sees the latest contract immediately
- The `openapi-regen` pre-commit hook auto-runs `make openapi` and stages the results whenever a backend router, schema, or `main.py` changes — so the spec and TS types can't drift locally
- `make openapi-check` (wired into `make lint-check` for CI) fails the build if either file is stale, catching anyone who bypasses hooks with `--no-verify`
- Prism reads that spec and serves mock responses matching the schema, with `--errors` so any spec-violating request body returns 422
- Integration tests (`*.integration.test.ts`) call methods on `api` and verify the real client↔contract round-trip
- Unit tests (`*.test.ts`) remain isolated with `vi.mock()` — no server needed
- The `dev:mock` mode sets `VITE_API_BASE_URL=http://localhost:4010/api/v1` via `.env.mock`
- `make openapi-check` (runs in CI via `make lint-check`) fails if either the spec or the generated TS types are stale
