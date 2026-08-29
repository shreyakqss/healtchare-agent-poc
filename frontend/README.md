# CareFlow frontend

Next.js 16 App Router, React 19, Tailwind v4, and strict TypeScript.

```bash
npm install
cp .env.example .env.local   # BACKEND_URL is server-only; defaults to http://localhost:8000
npm run dev
```

Keycloak login/logout is handled by `app/api/auth`; `app/api/careflow` is a fixed same-origin BFF. OAuth tokens never
enter browser JavaScript or local storage. Server pages enforce roles before fetching protected data, and unsafe browser
requests carry the CSRF token tied to the opaque HttpOnly CareFlow session.

Structure: `app/` routes → `features/<area>/` screen logic → `components/` shared UI → `lib/api` typed clients.
See [the architecture guide](../docs/ARCHITECTURE.md).
