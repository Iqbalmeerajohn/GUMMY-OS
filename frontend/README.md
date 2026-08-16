# GUMMY OS — Frontend

Next.js 16 (App Router, Turbopack) client for GUMMY. The chat **is** the app:
six routes total, with every other surface folded into slide-over panels behind
an icon rail.

## Run it

The backend must be running first (see [`../backend/README.md`](../backend/README.md)).

```bash
cd frontend
npm install
cp ../.env.example .env.local     # NEXT_PUBLIC_API_BASE_URL points at the backend
npm run dev                       # http://localhost:3000
```

`NEXT_PUBLIC_*` variables are inlined at build time — change one and rebuild.

## Checks (mirrors CI)

```bash
npx tsc --noEmit
npx eslint src
npm run build
```

## Routes

`/` (chat when signed in, landing when not) · `/login` · `/signup` ·
`/auth/callback` (Google OAuth fragment handoff) · `/icon.svg` · `/_not-found`

Panels behind the rail: Chats, Search (⌘K), Memory, Goals, Files, Agents,
Settings.

## Stack

React 19 · TypeScript · TanStack Query v5 (server state) · Zustand (light UI
state) · Tailwind CSS v4 · framer-motion · three / @react-three/fiber (the
living orb) · sonner (toasts).

Auth tokens come from the backend's own issuer; there is no auth SDK, no error
tracker, and no analytics SDK in this app — see
[M9 — Local-First GUMMY](../docs/10_RELEASE_NOTES_M9_LOCAL_FIRST.md).

> **Note:** this Next.js version has breaking changes from earlier releases.
> Read the relevant guide in `node_modules/next/dist/docs/` before writing code.
