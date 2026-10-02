# Frontend

Next.js App Router application for the Multi-Agent Task Orchestrator.

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
- `pnpm lint` — run ESLint
- `pnpm typecheck` — check TypeScript types
