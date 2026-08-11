# AI Resume Screening & Intelligent Candidate Shortlisting

An AI-powered platform with two flows:

- **Candidates** pick a target role, upload a resume, and get an ATS score, job-fit
  score, matched/missing skills and concrete suggestions.
- **Recruiters** pick a position, bulk-upload resumes, and get every candidate
  scored, ranked and bucketed into **Strong Match / Consider / Weak Match**, then
  interrogate the results with RAG ("Why was Rahul shortlisted?").

## Stack

| Layer | Choice |
| --- | --- |
| Frontend | React 18 + TypeScript + Vite |
| Backend | FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 |
| Database | PostgreSQL 16 (`pgvector` image, ready for Day 4) |
| Migrations | Alembic (async env) |
| Vector store | Qdrant (Day 4, `--profile vector`) |
| LLM | Groq (Llama 3.3 70B), forced tool-calling for structured extraction |
| Deployment | Docker + Docker Compose |

---

## Status — Day 2 complete

**Day 1** — foundation: job-role catalogue, database, upload pipeline.

- [x] Project scaffold, settings, structured error handling, logging
- [x] Database schema + async Alembic migrations (5 tables)
- [x] Job-role catalogue with 6 seeded roles and full matching vocabulary
- [x] Resume upload: candidate (single) and recruiter (bulk) flows
- [x] File validation (extension + magic bytes), size limits, SHA-256 de-duplication
- [x] Local storage with date sharding and path-traversal protection
- [x] React frontend for both flows

**Day 2** — resume and job-description parsing.

- [x] Local text extraction: PDF (`pypdf`), DOCX (`python-docx`), TXT/MD
- [x] LLM structured extraction via Groq, forced tool-calling against a Pydantic
      JSON schema (nested objects via `$defs` — no plain "JSON mode" guessing)
- [x] Provider-agnostic `LLMProvider` interface — swapping Groq for another
      provider later touches one factory function, not every call site
- [x] Parsing orchestration: text extraction always runs; the LLM step is queued
      as a `BackgroundTask` so uploads return immediately
- [x] Candidate creation/linking from parsed contact info, refreshed on re-parse
- [x] Job-description endpoints: create from pasted text or an uploaded file,
      list, get, manual re-parse
- [x] Manual re-parse endpoints for both resumes and job descriptions

**Verified end to end against the real Groq API**: a plain-text resume, a
hand-rolled genuinely-valid PDF, a real-world PDF from earlier manual testing,
and a pasted job description all parsed correctly — skills, experience,
education, and a linked `Candidate` row, all in one pass. Bulk upload parses
every file in a batch independently.

| Candidate flow | Recruiter flow |
| --- | --- |
| ![Candidate upload page](docs/screenshots/candidate.png) | ![Recruiter bulk upload page](docs/screenshots/recruiter.png) |

### Roadmap

| Day | Scope |
| --- | --- |
| 1 | Foundation, job roles, database, APIs, resume uploads ✅ |
| 2 | Resume + job-description parsing (PDF/DOCX text, LLM structured extraction) ✅ |
| 3 | ATS scoring |
| 4 | Semantic matching (BGE/E5 embeddings) + skill matching |
| 5 | Candidate ranking and shortlist categories |
| 6 | RAG, LLM explanations, recruiter AI chat |
| 7 | Evaluation benchmark, Dockerisation, docs, deployment |

---

## Quick start

### Prerequisites

Docker Desktop, Python 3.12+, Node 20+.

### 1. Environment

```bash
cp .env.example .env
```

> **Port note.** The Postgres container publishes on host port **5433**, not 5432, so
> it never collides with a locally installed Postgres. Change `POSTGRES_PORT` in
> `.env` if you prefer another port.

> **LLM parsing (optional but recommended).** Get a free key at
> [console.groq.com](https://console.groq.com) → API Keys, then set
> `GROQ_API_KEY` in `.env`. Without it, uploads still work — text extraction and
> storage happen normally — but the structured-extraction step is skipped
> rather than failed, and `parse_status` stays `pending`.

### 2. Database

```bash
docker compose up -d postgres
```

### 3. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
alembic upgrade head              # create the schema
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The six system job roles are seeded automatically on startup (idempotent — edit
`app/data/job_roles_seed.json` and restart to update them).

- API docs: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health>
- Readiness (checks the DB): <http://localhost:8000/health/ready>

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to the backend, so there is no
CORS setup in development.

### 5. Sample resumes (optional)

```bash
cd backend
python scripts/make_sample_resumes.py     # writes backend/sample_data/
```

Produces four realistic resumes as plain text, one as DOCX, one as a genuinely
valid hand-rolled PDF, and one file whose extension lies about its contents —
handy for exercising both the parsing path and the rejection path.

### Run everything in Docker

```bash
docker compose --profile full up -d --build
```

---

## Testing

```bash
cd backend
pytest -q
```

Tests run against a real Postgres so JSONB, UUID and constraint behaviour matches
production. A `resume_screening_test` database is created and dropped per run;
your dev data is never touched.

```
107 passed
```

Coverage: filename sanitisation, magic-byte sniffing, size limits, storage
round-trips and traversal guards, job-role CRUD, candidate upload + de-duplication,
recruiter bulk upload (partial-failure reporting), batch lifecycle, health probes,
text extraction (PDF/DOCX/TXT/MD, including a genuinely valid hand-rolled PDF
fixture), parsing orchestration (success/failure paths, candidate linking,
re-parse idempotency), job-description creation and parsing.

No test ever calls the real Groq API — a `FakeLLMProvider` fixture stands in for
it, so the suite runs offline and free. See "Design notes" below for how.

---

## API

Base path: `/api/v1`

### Job roles

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/job-roles` | List roles (`limit`, `offset`, `category`, `search`, `include_inactive`) |
| `GET` | `/job-roles/{slug\|id}` | Full role detail, including skills and scoring weights |
| `POST` | `/job-roles` | Create a custom role (slug generated from the title) |

### Candidate flow

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/resumes` | Upload one resume (`job_role_id` + `file`, multipart) — queues parsing |
| `GET` | `/resumes` | List/filter by role, batch, source, parse status |
| `GET` | `/resumes/{id}` | Resume record, including `parsed_data` once parsed |
| `GET` | `/resumes/{id}/download` | Original file |
| `POST` | `/resumes/{id}/parse` | Re-run text extraction + structured parsing |
| `DELETE` | `/resumes/{id}` | Delete the record and its stored file |

### Recruiter flow

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/batches` | Create a screening batch for a role |
| `GET` | `/batches` | List batches (filter by role or status) |
| `GET` | `/batches/{id}` | Batch with its resumes and role |
| `POST` | `/batches/{id}/resumes` | Bulk-upload (multipart `files`, up to 50) — queues parsing for each |
| `DELETE` | `/batches/{id}` | Delete the batch and everything in it |

### Job descriptions

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/job-descriptions` | Create from pasted text **or** an uploaded file (exactly one) |
| `GET` | `/job-descriptions` | List/filter by role or parse status |
| `GET` | `/job-descriptions/{id}` | Detail, including `raw_text` and `parsed_data` |
| `POST` | `/job-descriptions/{id}/parse` | Re-run structured extraction |

Job-description files aren't kept — only the text extracted from them — so
there's no matching `/download` route.

### Error format

Every failure returns the same envelope:

```json
{
  "error": {
    "code": "unsupported_file_type",
    "message": "'cv.pdf' does not appear to be a valid .pdf file.",
    "details": { "declared_extension": ".pdf" }
  }
}
```

Codes: `not_found` (404), `validation_error` / `request_validation_error` (422),
`unsupported_file_type` (415), `file_too_large` (413), `duplicate_resource` (409),
`internal_error` (500).

### Bulk upload is partially fault-tolerant

One malformed CV must not cost a recruiter the other 49. Each file is validated
independently and reported per row:

```json
{
  "received": 6, "uploaded": 4, "duplicates": 1, "rejected": 1,
  "items": [
    { "filename": "rahul.txt", "status": "uploaded",  "resume_id": "…" },
    { "filename": "rahul.txt", "status": "duplicate", "resume_id": "…" },
    { "filename": "fake.pdf",  "status": "rejected",
      "error_code": "unsupported_file_type", "error": "…" }
  ]
}
```

---

## Design notes

**De-duplication is scoped, not global.** Files are fingerprinted with SHA-256.
For recruiter uploads the scope is the batch; for candidate uploads it is the job
role — so the same CV submitted against a *different* role is a legitimately new
record, not a duplicate. A `UNIQUE (batch_id, content_hash)` constraint backs this
at the database level.

**Declared content types are not trusted.** A browser's `Content-Type` is advisory,
so every upload is checked against its magic bytes (`%PDF-` for PDF, the ZIP header
for DOCX, decodability for text). `fake.pdf` containing plain text is rejected.

**Skills live in JSONB, not a join table.** The matcher reads a role's vocabulary as
one document and never queries it field-by-field, so a join table would add cost
without buying anything.

**Storage is behind an interface.** `LocalResumeStorage` shards by `YYYY/MM`,
resolves every path against the storage root (rejecting traversal), and can be
swapped for S3/GCS without touching the API layer.

**Scoring weights ship with each role.** Each role carries its own
`scoring_weights` (`ats`, `required_skills`, `semantic`, `experience`) summing to
1.0 — a Business Analyst weights ATS keywords more heavily than an AI Engineer,
whose semantic fit matters more. A test enforces the normalisation.

**Parsing is forced tool-calling, not "JSON mode."** `ParsedResumeData` and
`ParsedJobDescriptionData` (in `app/schemas/`) are plain Pydantic models.
`model_json_schema()` on each becomes a Groq tool definition, and `tool_choice`
is forced to that exact tool — the model has no path to return prose instead of
structured data, and nested objects (experience entries, education entries) come
back correctly via `$defs` without any manual JSON-schema wrangling. The same
class then validates the response before it's persisted.

**The LLM sits behind an interface, like storage does.** `app/services/llm/`
defines `LLMProvider` (one method: text + a schema in, a validated model out)
and `get_llm_provider()` as the only way callers obtain one. `GroqProvider` is
the only implementation today; adding Ollama or Gemini later is a new class and
a one-line change to the factory, not a rewrite of the parsing service.

**Parsing runs as a `BackgroundTask`, not inline.** Uploading a resume returns
immediately with `parse_status: "pending"`; the LLM call happens after the
response is sent. `parse_resume`/`parse_job_description` open their own database
session rather than reusing the request's, since by the time a background task
runs, the request that queued it has already closed its own session. Bulk
uploads queue one task per successfully-ingested file — a rejected or duplicate
file is never queued.

**Tests never touch the real Groq API.** A `FakeLLMProvider` fixture
(`tests/conftest.py`) replaces `get_llm_provider()` for every test that goes
through the API layer, returning an empty-but-valid model by default or
whatever a test sets on `.response`/`.error`. This is also what makes the suite
safe to run without a `GROQ_API_KEY` at all.

---

## Project layout

```
.
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── alembic/               # async migration env + versions
│   ├── scripts/               # sample-resume generator (incl. a hand-rolled valid PDF)
│   ├── tests/                 # 107 tests against a real Postgres
│   └── app/
│       ├── api/v1/endpoints/  # health, job_roles, resumes, batches, job_descriptions
│       ├── core/              # settings, logging, error handling
│       ├── data/              # job_roles_seed.json
│       ├── db/                # base, session, seeder
│       ├── models/            # SQLAlchemy models + enums
│       ├── schemas/           # Pydantic request/response + parsed-data models
│       └── services/
│           ├── llm/           # LLMProvider interface, GroqProvider, factory
│           ├── text_extraction.py
│           ├── parsing_service.py   # orchestrates extraction -> LLM -> persist
│           ├── file_validation.py
│           ├── storage.py
│           └── resume_service.py
└── frontend/
    └── src/
        ├── api/               # typed client + shared types
        ├── components/        # RolePicker, FileDropzone
        └── pages/             # Home, Candidate, Recruiter
```

## Data model

| Table | Role |
| --- | --- |
| `job_roles` | Catalogue of screenable positions, skills, ATS keywords, weights |
| `job_descriptions` | Recruiter-supplied JDs — `raw_text` + `parsed_data`, populated on creation |
| `candidates` | People — created/refreshed by resume parsing |
| `resumes` | Uploaded files — `raw_text` + `parsed_data` populated by parsing |
| `screening_batches` | A recruiter's bulk run; groups resumes for ranking |

Columns for Days 3–5 (`analysis_status` and the scoring tables to come) already
exist or are additive, so those days add logic rather than destructive migrations.

## Troubleshooting

**`password authentication failed for user "resume"`** — a local Postgres is
occupying port 5432 and shadowing the container. The compose file publishes 5433
for exactly this reason; make sure `POSTGRES_PORT=5433` in `.env`.

**`ECONNREFUSED ::1:8000` from the Vite proxy** — Node resolves `localhost` to IPv6
first and uvicorn binds IPv4. The proxy target is pinned to `127.0.0.1`; if you
changed it, change it back.

**Job roles are empty** — run `alembic upgrade head`, then restart the API (seeding
runs on startup) or run `python -m app.db.seed`.

**A resume stays `pending` forever** — either `GROQ_API_KEY` isn't set (parsing is
silently skipped, not failed — see the note under Quick Start), or the Groq
free-tier rate limit was hit. Check `parse_error` on the resume once it's
`failed`, or re-trigger with `POST /resumes/{id}/parse`.

**Tests hang or fail at teardown with "Event loop is closed" (Windows only)** —
a known bad interaction between Windows' default `ProactorEventLoop` and
`asyncpg` when a fixture hands out a live DB connection the test body uses and
then touches again during its own teardown. `tests/conftest.py` works around it
by forcing the `SelectorEventLoop` policy and pinning `loop_scope="function"` on
any fixture that yields a live session (`test_engine`, `session`, `parsing_env`,
`client`). If you add a new fixture in that shape, give it the same treatment.
