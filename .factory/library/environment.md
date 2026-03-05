# Environment

Environment variables, external dependencies, and setup notes.

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `.factory/services.yaml`).

---

## Required Environment Variables

### LLM Providers
- `OPENROUTER_API_KEY` — Claude via OpenRouter
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME` — GPT-4.1
- `AZURE_GPT52_ENDPOINT`, `AZURE_GPT52_API_KEY` — GPT-5.2
- `AZURE_WHISPER_ENDPOINT`, `AZURE_WHISPER_API_KEY`, `AZURE_WHISPER_DEPLOYMENT_NAME` — Whisper speech-to-text

### Databases
- `DATABASE_URL` — Supabase PostgreSQL (client data, port 6543 pooler)
- `SYSTEM_DATABASE_URL` — Neon PostgreSQL (system data: auth, audit, config)
- `MCP_POSTGRES_CONNECTION_STRING` — MCP PostgreSQL server connection

### Application
- `SECRET_KEY` — JWT signing key
- `SEED_ADMIN_PASSWORD` — Initial admin account password
- `CORS_ALLOWED_ORIGINS` — Comma-separated allowed origins
- `ENVIRONMENT` — development / production

## Platform Notes (Windows)
- PowerShell aliases `curl` to `Invoke-WebRequest` — use `Invoke-RestMethod` for JSON APIs
- Python venv activation: `backend\venv\Scripts\activate` or direct `backend\venv\Scripts\python.exe`
- Line ending warnings (LF→CRLF) are cosmetic, git operations succeed
- Git push shows exit code 1 with stderr messages — push actually succeeds
- **OneDrive path workaround:** The Factory Create tool fails with `EEXIST: file already exists, mkdir` errors on paths containing spaces (e.g., `OneDrive - EY`). Workaround: use `Execute` with Python to write files (`open(path, 'w').write(content)`) then use `Edit` tool to refine, or write via PowerShell `.NET` methods (`[System.IO.File]::WriteAllText(path, content)`).
- **PowerShell template literal escaping:** Writing TypeScript files containing backtick template literals via PowerShell is problematic (backtick is PowerShell escape character). Use Python helper scripts to write such files instead.
- **File encoding:** Use UTF-8 without BOM. Several files had BOM characters removed in m1-auth-frontend. Do not re-introduce BOMs.
