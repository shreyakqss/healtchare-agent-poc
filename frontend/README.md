# CareFlow frontend

Next.js 16 (App Router) · React 19 · Tailwind v4 · TypeScript strict. No UI library: primitives live in
`src/components/ui`, tokens in `src/app/globals.css`.

```bash
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL, defaults to http://localhost:8000
npm run dev
```

Structure: `app/` routes only → `features/<area>/` screen logic → `components/` shared UI → `lib/api` typed client.
See `../docs/ARCHITECTURE.md`.