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
| Deployment | Docker + Docker Compose |

---

## Status — Day 1 complete

Day 1 delivers the foundation the rest of the build sits on.

- [x] Project scaffold, settings, structured error handling, logging
- [x] Database schema + async Alembic migrations (5 tables)
- [x] Job-role catalogue with 6 seeded roles and full matching vocabulary
- [x] Resume upload: candidate (single) and recruiter (bulk) flows
- [x] File validation (extension + magic bytes), size limits, SHA-256 de-duplication
- [x] Local storage with date sharding and path-traversal protection
- [x] React frontend for both flows
- [x] 70 passing tests against a real Postgres

**Verified end to end**: 6 roles seeded, uploads stored and de-duplicated, bad files
rejected with row-level reporting, downloads byte-identical to the original, and
the containerised stack (`--profile full`) migrating and serving on boot.

| Candidate flow | Recruiter flow |
| --- | --- |
| ![Candidate upload page](docs/screenshots/candidate.png) | ![Recruiter bulk upload page](docs/screenshots/recruiter.png) |

### Roadmap

| Day | Scope |
| --- | --- |
| 1 | Foundation, job roles, database, APIs, resume uploads ✅ |
| 2 | Resume + job-description parsing (PDF/DOCX text, LLM structured extraction) |
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

Produces four realistic resumes, a DOCX, and one file whose extension lies about
its contents — handy for exercising the rejection path.

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
70 passed
```

Coverage: filename sanitisation, magic-byte sniffing, size limits, storage
round-trips and traversal guards, job-role CRUD, candidate upload + de-duplication,
recruiter bulk upload (partial-failure reporting), batch lifecycle, health probes.

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
| `POST` | `/resumes` | Upload one resume (`job_role_id` + `file`, multipart) |
| `GET` | `/resumes` | List/filter by role, batch, source, parse status |
| `GET` | `/resumes/{id}` | Resume record |
| `GET` | `/resumes/{id}/download` | Original file |
| `DELETE` | `/resumes/{id}` | Delete the record and its stored file |

### Recruiter flow

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/batches` | Create a screening batch for a role |
| `GET` | `/batches` | List batches (filter by role or status) |
| `GET` | `/batches/{id}` | Batch with its resumes and role |
| `POST` | `/batches/{id}/resumes` | Bulk-upload (multipart `files`, up to 50) |
| `DELETE` | `/batches/{id}` | Delete the batch and everything in it |

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

---

## Project layout

```
.
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── alembic/               # async migration env + versions
│   ├── scripts/               # sample-resume generator
│   ├── tests/                 # 70 tests against a real Postgres
│   └── app/
│       ├── api/v1/endpoints/  # health, job_roles, resumes, batches
│       ├── core/              # settings, logging, error handling
│       ├── data/              # job_roles_seed.json
│       ├── db/                # base, session, seeder
│       ├── models/            # SQLAlchemy models + enums
│       ├── schemas/           # Pydantic request/response models
│       └── services/          # validation, storage, ingestion
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
| `job_descriptions` | Recruiter-supplied JDs, parsed on Day 2 |
| `candidates` | People — populated by resume parsing |
| `resumes` | Uploaded files, extraction state, scoring state |
| `screening_batches` | A recruiter's bulk run; groups resumes for ranking |

Columns for later days (`raw_text`, `parsed_data`, `parse_status`,
`analysis_status`) already exist, so Days 2–5 add logic rather than migrations.

## Troubleshooting

**`password authentication failed for user "resume"`** — a local Postgres is
occupying port 5432 and shadowing the container. The compose file publishes 5433
for exactly this reason; make sure `POSTGRES_PORT=5433` in `.env`.

**`ECONNREFUSED ::1:8000` from the Vite proxy** — Node resolves `localhost` to IPv6
first and uvicorn binds IPv4. The proxy target is pinned to `127.0.0.1`; if you
changed it, change it back.

**Job roles are empty** — run `alembic upgrade head`, then restart the API (seeding
runs on startup) or run `python -m app.db.seed`.
