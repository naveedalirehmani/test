# AEO Structure Comparison Prototype

A standalone tool to validate the proposed **brand-centric** parsing design
against the current **4-list** design — on the *same* answer-engine responses.

You give it a business context + a few prompts. For each prompt it:

1. Fetches the answer-engine response **once** (via DataForSEO).
2. Parses that one response **two ways** — current 4-list schema and the
   proposed brand-centric schema (this is the only step that differs).
3. Computes the comparable metrics for each and stores both.
4. Shows them **side by side** in the browser.

Because the raw response is shared, any difference you see is caused purely by
the instructor call (schema + prompt) and the downstream metric assembly — not
by two different AI answers.

## What it touches

- **Reads/writes** the same MongoDB as the platform (`MONGODB_URI`), but only
  its own collection: `aeo_compare_sessions`. Nothing else is modified.
- **Self-contained.** The analysis modules it needs (LLM fetch, instructor
  parsing, metrics) and the brand-centric modules under `poc/` are vendored
  into this package. No other server needs to be running.

## Prerequisites

A `.env` in this folder (copy `.env.example`) with: `MONGODB_URI`,
`MONGODB_DB_NAME`, `OPENAI_API_KEY`, `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`.

## Run (local)

```bash
cd backend/aeo_compare_prototype
python3.11 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -m uvicorn app:app --reload --port 8200
```

Open http://localhost:8200

For deploying to a VPS with Docker, see **DEPLOY_CONTABO.md**.

## Using it

1. Fill in the **business context** (name, website, brand names, industry,
   products). Brand names drive target-mention detection. Alternatively, paste
   an existing **business_id** to pull a real profile from the DB.
2. Pick provider(s) — start with just `chatgpt` (cheapest/fastest).
3. Enter your prompts (4 inputs by default; add/remove as needed).
4. Click **Analyze**. Results render side by side and are saved as a session
   (listed in the left sidebar for later).
5. **Re-parse** on a result re-runs both parses using the stored raw responses
   (no new fetches) — handy for iterating on the brand-centric schema/prompt.

## API

- `POST /api/analyze` — `{ business, prompts[], providers[] }` → session
- `GET /api/sessions` — recent session summaries
- `GET /api/sessions/{id}` — full session
- `POST /api/sessions/{id}/reparse` — re-parse from stored raw responses
- `GET /api/providers` — available providers
