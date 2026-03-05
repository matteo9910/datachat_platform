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

## Test Accounts (after M2 auth implementation)
- Admin: username `admin`, password from SEED_ADMIN_PASSWORD env var
- Analyst: create via admin panel after login
- User: create via admin panel after login

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
