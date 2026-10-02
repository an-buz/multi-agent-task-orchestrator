# Frontend

Next.js App Router application for the Multi-Agent Task Orchestrator.

The application targets Next.js 16 and requires Node.js 20.9 or later. The
development server and production build use Turbopack, which is the Next.js 16
default.

## Development

```bash
pnpm install
pnpm dev
```

The app runs at <http://localhost:3000>. Set `NEXT_PUBLIC_API_URL` in `.env.local` to change the API base URL.

## Project layout

- `src/app/` — routes, root layout, and global styles
- `src/components/` — shared UI and application providers
- `src/features/` — domain types and feature-specific state
- `src/lib/` — API client and shared utilities

## Scripts

- `pnpm dev` — start the development server
- `pnpm build` — create a production build
- `pnpm start` — serve the production build
- `pnpm lint` — run ESLint
- `pnpm typecheck` — check TypeScript types

Next.js 16 does not run ESLint during `next build`; run `pnpm lint` and
`pnpm typecheck` as separate checks.
