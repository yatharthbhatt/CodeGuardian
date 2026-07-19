# CodeGuardian AI — Frontend

React + TypeScript + Tailwind + Recharts dashboard for the tenant-scoped dashboard API
(`/api/v1/dashboard`). Built in **Phase 5**.

## Run

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api → http://localhost:8000)
npm run build      # typecheck + production build
```

> Note: this is a working scaffold committed as source. It is not built/run in the
> spec repo's offline test environment (no Node toolchain there); `npm install && npm run
> build` compiles it locally.

## Structure

```
frontend/
├── index.html                 # lang, color-scheme meta
├── src/
│   ├── main.tsx               # React root
│   ├── App.tsx                # shell: 11-view nav, theme toggle, skip-link
│   ├── theme.tsx              # light/dark (respects prefers-color-scheme, persists choice)
│   ├── index.css              # focus-visible rings, reduced-motion, skip-link
│   ├── api/client.ts          # bearer-auth API client (tenant comes from the token)
│   ├── components/StatCard.tsx
│   └── views/                 # Overview, CostAnalytics (Recharts) — pattern for the rest
├── tailwind.config.js         # class dark mode + AA-contrast risk palette
└── vite.config.ts
```

## Views (PRD §14)

Repository Overview · Open PRs · Risk Heatmap · Agent Decisions · Cost Analytics · Latency ·
Knowledge Graph · Technical Debt · Quality Timeline · Audit Log · Settings.

Overview + Cost Analytics are fully implemented; the remaining views follow the same
accessible pattern (TanStack Query hook → semantic table + Recharts chart).

## Accessibility (WCAG 2.2 AA)

- Semantic landmarks (`header`/`nav`/`main`), skip-to-content link, `aria-current` nav state.
- Data tables use `<caption>` + `scope`d headers; charts carry `role="img"` + `aria-label`
  and mirror their data in an accessible table.
- Visible keyboard focus rings (`:focus-visible`), `prefers-reduced-motion` support.
- Light/dark themes with AA-contrast colors; theme follows the OS and is user-toggleable.

## Auth

The dashboard API is OIDC/bearer authenticated and tenant-scoped from the token. In dev,
set a token via `setToken()` (see `src/api/client.ts`); production uses the OIDC login flow.
