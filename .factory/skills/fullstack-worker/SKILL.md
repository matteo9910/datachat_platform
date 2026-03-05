---
name: fullstack-worker
description: Full-stack worker for features requiring coordinated backend + frontend changes, deployment, and cross-cutting concerns
---

# Fullstack Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for features requiring BOTH backend and frontend changes:
- End-to-end feature implementation (API + UI)
- Deployment configuration (Docker, Vercel, Railway)
- Cross-cutting concerns (auth integration, environment config)
- Infrastructure setup (schema + API + UI)

## Work Procedure

1. **Read feature description.** Understand full scope (backend + frontend).

2. **Investigate existing code on BOTH sides.** Understand data flow end-to-end.

3. **Plan implementation order:** Schema → Backend API → Frontend API client → Frontend UI

4. **Backend tests first (RED):** `cd backend && venv\Scripts\python.exe -m pytest tests/ -v --tb=short`

5. **Implement backend (GREEN).**

6. **Frontend tests (RED):** `cd frontend && npx vitest run --reporter=verbose`

7. **Implement frontend (GREEN).**

8. **Type check:** `cd frontend && npx tsc --noEmit`

9. **Build:** `cd frontend && npm run build`

10. **End-to-end manual verification (CRITICAL):**
    - Test complete user flow in browser
    - Verify API calls succeed (network tab)
    - Test error cases
    - Test with different roles if auth-related

11. **Run ALL tests:** Backend + Frontend

## Example Handoff

```json
{
  "salientSummary": "Implemented KB feature end-to-end: CRUD API, ChromaDB training, KB page UI, Save to KB button in chat. 18 tests pass (10 backend, 8 frontend). Full flow verified in browser.",
  "whatWasImplemented": "Backend: GET/POST/PUT/DELETE /api/knowledge/pairs with ChromaDB training. Frontend: KnowledgeBasePage, SaveToKBButton in chat, knowledgeApi.ts",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": "cd backend && venv\\Scripts\\python.exe -m pytest tests/test_knowledge.py -v", "exitCode": 0, "observation": "10 tests passed" },
      { "command": "cd frontend && npx tsc --noEmit", "exitCode": 0, "observation": "No type errors" },
      { "command": "cd frontend && npm run build", "exitCode": 0, "observation": "Build successful" }
    ],
    "interactiveChecks": [
      { "action": "Navigate to KB page", "observed": "Empty state with Add button" },
      { "action": "Add pair manually", "observed": "Pair appears in list" },
      { "action": "Save from chat", "observed": "Modal opens with pre-filled data" },
      { "action": "Delete pair", "observed": "Removed after confirmation" }
    ]
  },
  "tests": { "added": [
    { "file": "backend/tests/test_knowledge.py", "cases": [
      { "name": "test_create_pair", "verifies": "POST creates pair" },
      { "name": "test_delete_pair", "verifies": "DELETE removes pair" }
    ]}
  ]},
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Feature scope larger than ~2 hours of work
- External service not available (DB, Railway, etc.)
- Architecture decision needed
- Deployment fails for infrastructure reasons