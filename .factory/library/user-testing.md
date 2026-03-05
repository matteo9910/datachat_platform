# User Testing

Testing surface: tools, URLs, setup steps, isolation notes, known quirks.

**What belongs here:** How to manually test the app, what tools to use, test account setup, known testing limitations.

---

## Testing Surface

### Local Development
- Backend: http://localhost:8000
- Frontend: http://localhost:5173
- Health check: GET http://localhost:8000/health

### Production (after deploy)
- Backend: Railway URL (TBD after deploy)
- Frontend: Vercel URL (TBD after deploy)

## Testing Tools
- **agent-browser**: For UI testing (login flows, chat, gallery, dashboard, settings)
- **curl / Invoke-RestMethod**: For API endpoint testing
- **Browser DevTools**: For network inspection, console errors, SSE streaming verification

## Test Accounts (created and verified)
- **Admin:** email=`admin@datachat.local`, password=`<set via SEED_ADMIN_PASSWORD env var>`, role=admin (seed account, auto-created on first run)
- **Analyst:** email=`analyst1@test.local`, password=`<set via admin API>`, role=analyst (created via admin API)
- **User 1:** email=`user1@test.local`, password=`<set via admin API>`, role=user (created via admin API)
- **User 2:** email=`user2@test.local`, password=`<set via admin API>`, role=user (created via admin API, for disable/enable testing)

## Setup Steps for Testing
1. Ensure backend is running (port 8000)
2. Ensure frontend is running (port 5173)
3. Open http://localhost:5173 in browser
4. Complete Setup Wizard if first run (select Supabase, enter connection string, select tables, select LLM provider)
5. After M2: Login required before Setup Wizard

## Known Testing Quirks
- SSE streaming in chat requires EventSource API support
- Plotly charts need DOM to render (headless testing may not show chart visuals)
- ChromaDB initialization takes 5-10 seconds on first query
- Azure Whisper API has ~1-3 second latency for transcription
- Voice testing requires microphone hardware (may not work in CI)
- **SYSTEM_DATABASE_URL is now configured** — System DB (Supabase pooler) is reachable. Auth endpoints work. Seed admin created on startup. Login returns JWT tokens. All auth flows unblocked.
- Frontend vite dev server takes ~15 seconds to start. Use `Start-Process -FilePath "node" -ArgumentList "path\to\vite.js", "--port", "5173" -WorkingDirectory "frontend" -WindowStyle Hidden` to start it as a detached process.
- Backend startup: `Start-Process -FilePath "backend\venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" -WorkingDirectory "backend"`

## Flow Validator Guidance: Web UI

### Testing Tool
Use the `agent-browser` skill for all browser-based UI testing.

### Isolation Rules
- Each flow validator subagent should use its own browser session (via --session flag)
- Since the system DB is NOT reachable, auth flows will fail — login will return 500 errors
- Test what CAN be tested: login page rendering, unauthenticated redirect behavior, form existence
- Do NOT attempt to create real user accounts — the system DB is unavailable

### Boundaries
- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health
- All protected API routes return 401 without token (verifiable)
- All auth API routes (login, admin CRUD) return 500 due to system DB placeholder

## Flow Validator Guidance: API

### Testing Tool
Use curl/Invoke-RestMethod for API endpoint testing.

### Verifiable Without System DB
- GET /health → 200
- GET /api/admin/users (no auth) → 401
- POST /api/admin/users (no auth) → 401
- POST /api/auth/login → 500 (system DB unavailable)

### Now Unblocked (System DB is live)
- All login/logout flows (POST /api/auth/login, /api/auth/logout)
- All user CRUD operations (GET/POST/PUT /api/admin/users)
- All role-based access control verification (403 for insufficient roles)
- Account disable/enable flows (PUT /api/admin/users/{id} with is_active)
- Duplicate email rejection (POST /api/admin/users with existing email -> 409)
- Self-disable prevention (PUT /api/admin/users/{own_id} with is_active=false -> 400)

### API Endpoints Reference
- POST /api/auth/login - body: {email, password} -> {token, user}
- POST /api/auth/logout - header: Authorization Bearer {token} -> {message}
- GET /api/admin/users - header: Bearer {admin_token} -> [{user}]
- POST /api/admin/users - header: Bearer {admin_token}, body: {email, password, full_name, role} -> {user}
- PUT /api/admin/users/{id} - header: Bearer {admin_token}, body: {role?, full_name?, is_active?} -> {user}
- GET /api/admin/users/{id} - header: Bearer {admin_token} -> {user}
