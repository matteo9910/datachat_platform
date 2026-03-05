---
name: backend-worker
description: Python/FastAPI backend implementation worker for API endpoints, services, database models, and infrastructure
---

# Backend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for features that are primarily backend work:
- API endpoints (FastAPI routers)
- Service layer logic (business logic, LLM integration, RAG pipeline)
- Database models and migrations (SQLAlchemy + Alembic)
- Authentication/authorization middleware
- Docker configuration and deployment files

## Work Procedure

1. **Read feature description and preconditions.** Understand what endpoints/services to build.

2. **Read existing code in the relevant area:**
   - `backend/app/main.py` — router registration, middleware
   - `backend/app/config.py` — settings loading
   - Existing routers in `backend/app/api/` — follow conventions
   - Existing services in `backend/app/services/` — follow patterns
   - `backend/requirements.txt` — installed packages

3. **Write tests first (RED).** In `backend/tests/`:
   - pytest with FastAPI TestClient
   - Test success, error, and edge cases
   - Test auth (401 without token, 403 wrong role)
   - Run: `cd backend && venv\Scripts\python.exe -m pytest tests/ -v --tb=short`
   - Confirm tests FAIL

4. **Implement (GREEN).** Minimal code to pass tests:
   - Routers in `backend/app/api/`, services in `backend/app/services/`
   - Register routers in `main.py`
   - Add deps to `requirements.txt` if needed

5. **Manual verification.** Test with curl/Invoke-RestMethod.

6. **Run full test suite.** Ensure no regressions.

## Example Handoff

```json
{
  "salientSummary": "Implemented JWT auth with login/logout, user CRUD, and role middleware. 12 tests pass. Verified login flow and 401/403 responses manually.",
  "whatWasImplemented": "POST /api/auth/login, POST /api/auth/logout, GET/POST/PUT /api/admin/users, auth middleware, bcrypt hashing, 3 roles in JWT claims",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": "cd backend && venv\\Scripts\\python.exe -m pytest tests/test_auth.py -v", "exitCode": 0, "observation": "12 tests passed" }
    ],
    "interactiveChecks": [
      { "action": "POST /api/auth/login with invalid password", "observed": "Returns 401" },
      { "action": "GET /api/admin/users without token", "observed": "Returns 401" },
      { "action": "GET /api/admin/users with Analyst JWT", "observed": "Returns 403" }
    ]
  },
  "tests": {
    "added": [
      { "file": "backend/tests/test_auth.py", "cases": [
        { "name": "test_login_success", "verifies": "Valid credentials return JWT" },
        { "name": "test_login_invalid", "verifies": "Wrong password returns 401" },
        { "name": "test_protected_no_token", "verifies": "Missing auth returns 401" },
        { "name": "test_admin_only_with_analyst", "verifies": "Analyst on admin endpoint returns 403" }
      ]}
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Feature requires frontend changes
- Database schema prerequisite not met
- Required environment variable missing
- Existing bugs block this feature