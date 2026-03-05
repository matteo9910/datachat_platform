---
name: frontend-worker
description: React/TypeScript frontend worker for UI components, pages, state management, and Vercel config
---

# Frontend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for features that are primarily frontend work:
- React components and pages
- Zustand store updates
- API client functions
- Plotly chart rendering and branding
- Vercel deployment configuration

## Work Procedure

1. **Read feature description and preconditions.**

2. **Read existing code:**
   - `frontend/src/App.tsx` — routing, layout
   - `frontend/src/components/Sidebar.tsx` — navigation
   - Existing components in feature area
   - `frontend/src/api/` — API client patterns
   - `frontend/src/store/appStore.ts` — state management
   - `frontend/package.json` — dependencies

3. **Write tests first (RED):**
   - vitest + @testing-library/react
   - Run: `cd frontend && npx vitest run --reporter=verbose`

4. **Implement (GREEN).** Minimal code to pass tests:
   - Components in `frontend/src/components/{Feature}/`
   - API functions in `frontend/src/api/`
   - State in Zustand stores
   - Update routing in App.tsx, Sidebar.tsx if needed
   - Use Tailwind CSS

5. **Type check:** `cd frontend && npx tsc --noEmit`

6. **Manual verification.** Open browser, test all interactions.

7. **Build check:** `cd frontend && npm run build`

## Example Handoff

```json
{
  "salientSummary": "Implemented login page with form validation, JWT storage, and protected routes. TypeScript clean, build succeeds, verified login/logout in browser.",
  "whatWasImplemented": "LoginPage component, AuthProvider context, ProtectedRoute wrapper, Sidebar auth gating, API interceptor for Authorization header",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": "cd frontend && npx tsc --noEmit", "exitCode": 0, "observation": "No type errors" },
      { "command": "cd frontend && npm run build", "exitCode": 0, "observation": "Build successful" }
    ],
    "interactiveChecks": [
      { "action": "Open localhost:5173 in incognito", "observed": "Redirected to /login" },
      { "action": "Login with valid credentials", "observed": "Main app loads, role badge visible" },
      { "action": "Refresh page", "observed": "Stays logged in" },
      { "action": "Click logout", "observed": "Redirected to login, token cleared" }
    ]
  },
  "tests": { "added": [] },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Required API endpoint does not exist
- UX decision needed not in feature spec
- Package dependency conflict