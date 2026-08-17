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
| Database | PostgreSQL 16 + `pgvector` extension (vector storage/search lives in the same DB) |
| Migrations | Alembic (async env) |
| Embeddings | `BAAI/bge-small-en-v1.5` via `sentence-transformers`, local CPU inference |
| LLM | Groq (`openai/gpt-oss-120b`), forced tool-calling for structured extraction |
| Deployment | Docker + Docker Compose |

---

## Status — Day 5 complete

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
- [x] Recruiter UI step to attach a job description (paste or upload) to a batch

**Day 3** — ATS scoring.

- [x] `resume_scores` table, one row per resume, refreshed on re-score — built
      wide enough up front (`semantic_score`, `final_score`, `category` columns
      already present but null) that Days 4-5 add logic, not migrations
- [x] ATS keyword coverage: literal, case-insensitive scan of a role's
      `ats_keywords` against the resume's extracted raw text
- [x] Required-skill match: parsed resume skills vs. a role's required/preferred
      skills, producing a percentage plus matched/missing skill lists
- [x] Experience fit: candidate's parsed years vs. a role's min/max, with an
      unstated year treated as neutral (50%) rather than a penalty
- [x] If a batch is linked to a specific job description (see Day 2's UI
      addition), its parsed required/preferred skills are merged into the
      scoring vocabulary automatically
- [x] Rule-based improvement suggestions (missing skills, thin ATS coverage, no
      stated experience/education) — no LLM call, this is pure computation
- [x] Scoring runs automatically as soon as parsing succeeds, and manually via
      `POST /resumes/{id}/score`
- [x] All 6 seeded roles' `min_experience_years` set to 0 — nobody is filtered
      out purely for being junior; experience only affects the score

**Verified end to end against the real Groq API and Postgres**: uploaded a real
resume, watched it parse then auto-score, and inspected the exact matched/missing
skills and suggestions. Along the way this surfaced a genuine bug — see "Design
notes" — that's now fixed and covered by a regression test.

**Day 4** — semantic matching.

- [x] Whole-profile embeddings via `BAAI/bge-small-en-v1.5` (`sentence-transformers`),
      running locally on CPU — free, no API key, no rate limits
- [x] Embeddings stored and compared using **pgvector** directly in Postgres — no
      separate vector-store service; the `qdrant` service scaffolded in Day 1's
      `docker-compose.yml` was removed once this decision was made
- [x] `semantic_score`: cosine similarity between a resume's profile embedding and
      its role's (and/or linked JD's) embedding, rescaled from the model's
      realistic similarity range into an intuitive 0-100
- [x] `final_score` now blends `ats` + `required_skills` + `experience` +
      `semantic` using a role's full configured weights, instead of dropping
      `semantic`'s share as Day 3 had to
- [x] Role/JD embeddings computed once and reused — at seed time for system
      roles, right after parsing for JDs, lazily backfilled for custom roles
      created via the API
- [x] Embedding model warms up at app startup so the first real score isn't the
      request that pays the multi-second load cost
- [x] **A calibration finding that changed the plan**: bare skill-name-to-skill-name
      embedding comparison ("Vector Databases" vs "FAISS") does *not* reliably
      separate true matches from false ones with this model — tested and
      rejected empirically before writing any scoring code. Semantic matching
      here operates on whole profile/role text only; see "Design notes."

**Verified end to end against the real BGE model**: a strong-fit resume scored
93% semantic / 77.1% overall (up from a literal-only 57%); a genuinely
mismatched resume (Business Analyst against an AI Engineer role) correctly
scored 51.5% semantic / 35.5% overall; a custom role created via the API with
no pre-computed embedding correctly backfilled one on first score.

**Day 5** — candidate ranking and shortlist categories.

- [x] `category`: every scored resume is bucketed into **Strong Match**
      (`final_score` ≥ 75), **Consider** (≥ 45) or **Weak Match** (below 45) —
      fixed global thresholds, not per-role, computed right alongside
      `final_score` in `scoring_service.py`
- [x] `GET /batches/{id}` now returns resumes **ranked by `final_score`**
      (descending) instead of upload order; resumes still parsing/scoring (or
      that failed either step) sort last rather than interrupting the ranking
- [x] `category_counts` on the batch response (`strong_match` / `consider` /
      `weak_match` / `unscored`) — a recruiter-facing summary without having
      to count badges by hand
- [x] Recruiter UI: a **Ranked results** section (polls until scoring settles,
      the same pattern the candidate page already used for its own polling)
      showing the category-counts stat row and a ranked table with
      color-coded category badges

**Verified end to end in the browser** (Playwright, headless Chromium, real
backend/Postgres/Groq/BGE — see `docs/screenshots/`): uploaded three resumes
against the AI Engineer role and watched them settle into 87% Strong Match,
51% Consider and 23% Weak Match, correctly ranked and color-coded. This also
surfaced two real, unrelated bugs — see "Design notes":
1. `POST /resumes/{id}/score` could return a **stale score** in its own
   response (the DB was updated correctly; only the echoed-back JSON was
   wrong) — a SQLAlchemy identity-map issue, now fixed and regression-tested.
2. Groq had decommissioned `llama-3.3-70b-versatile` (the model this project
   shipped with) — parsing was failing outright. Swapped to
   `openai/gpt-oss-120b`, verified against the live API.

| Candidate flow | Recruiter flow |
| --- | --- |
| ![Candidate upload page](docs/screenshots/candidate.png) | ![Recruiter bulk upload page](docs/screenshots/recruiter.png) |

### Roadmap

| Day | Scope |
| --- | --- |
| 1 | Foundation, job roles, database, APIs, resume uploads ✅ |
| 2 | Resume + job-description parsing (PDF/DOCX text, LLM structured extraction) ✅ |
| 3 | ATS scoring ✅ |
| 4 | Semantic matching (embeddings via pgvector) ✅ |
| 5 | Candidate ranking and shortlist categories ✅ |
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

> **Semantic matching needs no key** — `sentence-transformers` runs the
> embedding model locally. First install pulls in torch (CPU build, a genuinely
> large download); first run downloads the ~130MB model from Hugging Face
> (skipped entirely if you build the Docker image, which pre-downloads it).

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
181 passed
```

Coverage: filename sanitisation, magic-byte sniffing, size limits, storage
round-trips and traversal guards, job-role CRUD, candidate upload + de-duplication,
recruiter bulk upload (partial-failure reporting), batch lifecycle, health probes,
text extraction (PDF/DOCX/TXT/MD, including a genuinely valid hand-rolled PDF
fixture), parsing orchestration (success/failure paths, candidate linking,
re-parse idempotency), job-description creation and parsing, ATS/skill/experience
scoring math (parametrised against known inputs), JD-vocabulary merging, a
schema-level regression test locking in the null-list Groq fix described below,
semantic-score math and weight blending, embedding-text builders, the seed
embedding backfill (idempotent — re-seeding unchanged roles doesn't re-embed them),
shortlist-category threshold boundaries, and batch ranking/category-counts
(including that unscored resumes sort last and count separately).

No test ever calls the real Groq API or downloads the real embedding model — a
`FakeLLMProvider` and `FakeEmbeddingProvider` stand in for both, so the suite
runs offline, free, and fast. See "Design notes" below for how.

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
| `GET` | `/resumes/{id}` | Resume record, including `parsed_data` and `score` once ready |
| `GET` | `/resumes/{id}/download` | Original file |
| `POST` | `/resumes/{id}/parse` | Re-run text extraction + structured parsing |
| `POST` | `/resumes/{id}/score` | Re-run ATS scoring (synchronous — no LLM call to wait on) |
| `DELETE` | `/resumes/{id}` | Delete the record and its stored file |

Scoring runs automatically right after a successful parse, so in the normal
flow you never need to call `/score` yourself — it exists for recomputing
after, say, editing a role's required skills.

### Recruiter flow

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/batches` | Create a screening batch for a role (optionally linked to a JD) |
| `GET` | `/batches` | List batches (filter by role or status) |
| `GET` | `/batches/{id}` | Batch with its resumes — ranked by `final_score` descending — plus `category_counts` and role |
| `POST` | `/batches/{id}/resumes` | Bulk-upload (multipart `files`, up to 50) — queues parsing + scoring for each |
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

### Scoring

Every parsed resume carries a `score` object once scoring completes:

```json
{
  "ats_score": 25.0,
  "matched_ats_keywords": ["LLM", "transformer", "inference", "evaluation"],
  "required_skill_match": 72.7,
  "matched_skills": ["Python", "RAG", "LangChain", "FastAPI", "Docker", "…"],
  "missing_skills": ["Vector Databases", "REST API", "Git"],
  "experience_match": 100.0,
  "candidate_experience_years": 4.0,
  "suggestions": [
    "Good news first: Python, RAG, LangChain, FastAPI, Docker all came through clearly, and they're exactly what this role is looking for. …",
    "You're missing a few skills this role looks for: Vector Databases, REST API, Git. …",
    "Automated screening for this role commonly looks for terms like GPT, Claude, retrieval augmented generation. …"
  ],
  "semantic_score": 93.0,
  "final_score": 77.1,
  "category": "strong_match"
}
```

This is a real, unedited result. Note the gap between `ats_score` (25%) and
`semantic_score` (93%): the candidate's resume lists FAISS, Qdrant and Pinecone
but not the literal phrase "Vector Databases", so keyword scanning alone
penalises a candidate who clearly has the underlying skill. `final_score`
(77.1%) blends both signals using the role's configured weights, landing on a
fairer overall number than either alone. `category` (Day 5) is one of
`strong_match` / `consider` / `weak_match`, derived directly from
`final_score` — see "Design notes" for the thresholds.

A batch's `GET /batches/{id}` response includes a `category_counts` summary
alongside its (now ranked) `resumes` array:

```json
{
  "category_counts": {
    "strong_match": 4,
    "consider": 9,
    "weak_match": 12,
    "unscored": 2
  }
}
```

`unscored` covers resumes still parsing/scoring, or that failed either step —
the four counts always add up to the batch's total resume count.

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

**Scoring is pure computation, deliberately.** `scoring_service.py` makes zero
network calls — no LLM, no embeddings. Day 3's job is the classic ATS behaviour
(literal keyword scanning, exact-ish skill-list overlap), which is fast,
free, and fully deterministic; that's also why it's tested with plain
parametrised unit tests rather than a `FakeLLMProvider`. Day 4 adds the
semantic layer *on top* of this, not instead of it — a resume can score low on
Day 3's literal match and still recover on Day 4's semantic similarity.

**A linked job description extends the vocabulary, it doesn't replace it.**
When a recruiter attaches a specific JD to a batch, its parsed
`required_skills`/`preferred_skills` are merged into the role's own lists
(deduplicated) before scoring — a candidate is measured against the role's
general expectations *and* whatever this particular posting adds, not just one
or the other.

**The `resume_scores` table was designed for Days 3-5 up front.** `semantic_score`,
`final_score` and `category` exist as nullable columns already, populated by
nothing yet. This mirrors the same choice made for `Resume.parsed_data` back on
Day 1: define the shape once, let later days fill it in, and avoid three more
migrations for what is conceptually one entity (a resume's score against a role).

**A real bug, caught by testing against the live API, not just mocks.** Every
list field in `ParsedResumeData`/`ParsedJobDescriptionData` was originally typed
as plain `list[str]` with a default of `[]`. Groq's structured-output validation
is strict against the JSON schema it's given — when the model emitted `null`
for an empty `education` list instead of `[]`, Groq itself rejected the tool
call with a 400 *before* the response ever reached our code:
`` `/education`: expected array, but got null ``. Every list field's type is
now `list[T] | None` (so the schema handed to Groq permits null) with a
`field_validator(mode="before")` that normalises `None` back to `[]`, so nothing
downstream has to special-case it. `tests/test_parsed_data_schemas.py` asserts
every list field's generated schema permits null and that null validates to
`[]`, so this can't silently regress. This is exactly why the "verify against
the real API" step earlier in this session mattered — the mocked test suite
was green throughout; only a live call surfaced it.

**pgvector, not a separate vector-store service.** Day 1 scaffolded a Qdrant
service in `docker-compose.yml` "just in case." Day 4 didn't use it: the
`pgvector/pgvector:pg16` image was already the Postgres in use, so enabling its
`vector` extension (one migration: `CREATE EXTENSION IF NOT EXISTS vector`) and
adding `vector(384)` columns via the `pgvector` Python package's SQLAlchemy
integration meant embeddings live in the same database and transaction as
everything else — no second service to run, back up, or keep in sync. The
unused Qdrant scaffold was removed rather than left as dead-but-plausible
infrastructure.

**Bare skill-to-skill embedding comparison was tested and rejected — this
mattered enough to check before writing any scoring code.** The obvious way to
fix "Vector Databases" not literally matching "FAISS" would be to embed each
missing skill and each of the resume's skills, then treat a high cosine
similarity as a match. Empirically, this doesn't work with a general-purpose
sentence embedding model: `Python <-> JavaScript` (unrelated) scored *higher*
(0.72-0.85 across several prompt templates) than `Vector Databases <-> FAISS`
(the exact case being fixed, 0.49-0.78). These models capture broad topical
similarity ("both are tech terms") far more reliably than precise
category-vs-specific-instance relationships, which is a different kind of
question. Whole-*document* comparison, by contrast, separates cleanly — a
matching resume/role pair landed at 0.85, a wrong-field resume at 0.60,
unrelated text at 0.39, correctly ordered and workable. That's why semantic
matching here compares whole profile/role text only, not individual skills;
Day 3's literal `missing_skills` list is unchanged and still exact-match.

**Raw cosine similarity needed rescaling to read as a 0-100 score.** BGE-small
doesn't spread related text across the full 0-1 range — even unrelated text
lands around 0.39, so a plain `similarity * 100` would make an irrelevant
resume look like a 39% match. `_score_semantic` rescales using an empirically
chosen floor (0.35) and ceiling (0.90) derived from the calibration points
above, clamped to 0-100. This is a reasonable estimate, not a rigorously tuned
threshold — Day 7's evaluation benchmark (Precision/Recall/NDCG@K against
keyword vs. embedding vs. hybrid matching) is the right place to refine it
against labelled data if it turns out to need adjustment.

**A linked JD's embedding blends with the role's, it doesn't replace it** —
same "extend, don't replace" philosophy as the Day 3 skill-vocabulary merge.
When both exist, the two embeddings are averaged before comparing to the
resume; when only one exists, that one is used directly.

**Custom roles get their embedding backfilled lazily.** Seeded system roles are
embedded up front (`app/db/seed.py`), but a role created via `POST /job-roles`
isn't — `scoring_service.py` computes and persists one the first time that role
is actually scored against, so there's no separate "remember to embed new
roles" step to forget.

**The embedding model is warmed up at startup, and its import is lazy for a
concrete reason.** `sentence-transformers` transitively imports `torch`, which
takes several seconds. Importing it at module level in
`app/services/embedding/bge_provider.py` — even before anything called
`get_embedding_provider()` — added that cost to *every* import of the module,
including `app.main`, Alembic runs, and test collection: a 43-second `import
app.main` was caught and fixed by moving the `sentence_transformers` import
inside `BgeEmbeddingProvider.__init__`, where it's paid exactly once, when the
provider is actually constructed. That construction now happens deliberately at
app startup (`WARM_UP_EMBEDDING_MODEL`, default on) so the first real resume
score isn't the request that eats a multi-second cold load.

**Tests fake the embedding provider the same way they fake the LLM.**
`FakeEmbeddingProvider` (`tests/conftest.py`) produces deterministic,
unit-length vectors seeded from a hash of the input text — enough to test that
`semantic_score` gets computed, persisted, and correctly folded into
`final_score`, without downloading a model or asserting on real semantic
quality (that was validated separately, against the real model, in the
calibration work described above).

**Shortlist thresholds are fixed global constants, not per-role config.**
`_STRONG_MATCH_THRESHOLD` (75) and `_CONSIDER_THRESHOLD` (45) in
`scoring_service.py` bucket every role's `final_score` the same way. Nothing
in the spec called for per-role tuning, and a role's `scoring_weights` already
gives each role its own notion of what a "good" score looks like before the
bucket cutoff is even applied — adding a second, per-role knob on top would be
tuning the same thing twice. These are as reasoned-about-but-unvalidated as
Day 4's semantic floor/ceiling; Day 7's evaluation benchmark is the place to
revisit them against real labelled data.

**Ranking sorts scored resumes first, unscored ones last, deterministically.**
`_rank_key` in `app/api/v1/endpoints/batches.py` returns a tuple —
`(has_no_score, -final_score, created_at)` — rather than special-casing `None`
inside a comparator. Resumes with no score yet (still parsing/scoring, or
failed either step) group at the end, oldest-uploaded first among themselves,
so a recruiter refreshing mid-batch sees a stable order rather than results
reshuffling as scores trickle in.

**A stale-score bug in the manual re-score endpoint, caught by driving the UI
with a real browser, not just curl.** `POST /resumes/{id}/score` loads a
resume (eager-loading its `.score` relationship), calls `score_resume()` —
which deliberately opens its *own* database session so it can also run as a
detached background task — and then re-fetched the resume through the
*original* session to build the response. SQLAlchemy's identity map doesn't
overwrite already-loaded relationship data on a plain re-`select()`, so the
response echoed back the pre-update score even though the database itself was
updated correctly. Reproduced with a strengthened assertion in
`test_rescore_recomputes_the_score` (`scored_at >` instead of `>=`, which the
bug happily satisfied), fixed with a `session.expire_all()` before the
re-fetch in `app/api/v1/endpoints/resumes.py`.

**Groq decommissioned the model this project shipped with, mid-project.**
`llama-3.3-70b-versatile` (Day 2's default `GROQ_MODEL`) started returning
`404 model_not_found` — not a bug in this codebase, but it silently broke
every real parse/score request. Caught by actually driving the recruiter flow
in a browser rather than trusting the test suite (which never calls the real
API). Queried Groq's live `/models` endpoint with the project's own key,
confirmed `openai/gpt-oss-120b` both exists and honours forced `tool_choice`
correctly, and made it the new default. If this happens again: any model
Groq lists as `active: true` that supports tool calling is a candidate — check
with a direct forced-tool-call request before trusting it, the same way this
one was checked.

---

## Project layout

```
.
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── alembic/               # async migration env + versions
│   ├── scripts/               # sample-resume generator (incl. a hand-rolled valid PDF)
│   ├── tests/                 # 181 tests against a real Postgres
│   └── app/
│       ├── api/v1/endpoints/  # health, job_roles, resumes, batches, job_descriptions
│       ├── core/              # settings, logging, error handling, constants.py (EMBEDDING_DIMENSIONS)
│       ├── data/              # job_roles_seed.json
│       ├── db/                # base, session, seeder (embeds new/changed roles)
│       ├── models/            # SQLAlchemy models + enums (incl. resume_score.py)
│       ├── schemas/           # Pydantic request/response + parsed-data models
│       └── services/
│           ├── llm/                 # LLMProvider interface, GroqProvider, factory
│           ├── embedding/            # EmbeddingProvider interface, BgeEmbeddingProvider, factory
│           ├── embedding_text.py     # builds the text each entity type embeds
│           ├── text_extraction.py
│           ├── parsing_service.py   # orchestrates extraction -> LLM -> persist -> score
│           ├── scoring_service.py   # ATS + skill + experience + semantic scoring
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
| `job_roles` | Catalogue of screenable positions, skills, ATS keywords, weights, `embedding` |
| `job_descriptions` | Recruiter-supplied JDs — `raw_text` + `parsed_data` + `embedding` |
| `candidates` | People — created/refreshed by resume parsing |
| `resumes` | Uploaded files — `raw_text` + `parsed_data` + `embedding` |
| `resume_scores` | One row per resume — ATS/skill/experience/semantic/final scores + `category` |
| `screening_batches` | A recruiter's bulk run; groups resumes for ranking |

`embedding` columns are `vector(384)` (pgvector), populated by Day 4.
`category` on `resume_scores` (Day 5) is populated the same way `final_score`
is — every column on this table was reserved up front back on Day 3 and each
later day added logic against an existing column, never another migration.

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

**`parse_error` says `model_not_found` / "The model `...` does not exist or you
do not have access to it"** — Groq retired the model `GROQ_MODEL` points at
(this has already happened once — the project shipped with
`llama-3.3-70b-versatile`, which Groq later decommissioned). List what your key
can currently use with `client.models.list()` (any `active: true` entry that
supports tool calling is a candidate), verify it honours forced `tool_choice`
with a quick direct request, then update `GROQ_MODEL`.

**`parse_error` mentions "tool call validation failed" / "expected array, but
got null"** — a new field was added to `ParsedResumeData` or
`ParsedJobDescriptionData` typed as a plain `list[...]` rather than
`list[...] | None`. Groq's own schema validation rejects a `null` response
against a schema that only allows an array. Type it as `list[T] | None` and add
it to that model's `_null_list_becomes_empty` validator — see "Design notes."

**`semantic_score` is `null`, or app startup logs "Embedding model warm-up
failed"** — the model couldn't load. Check Hugging Face Hub connectivity (first
run needs to download ~130MB; subsequent runs use the local cache but still
check for updates). Set `WARM_UP_EMBEDDING_MODEL=false` to boot without it
temporarily — scores still compute, just without the semantic component,
identically to how `final_score` behaves when a role has no embedding yet.

**A plain import of `app.main` (or running any test) suddenly takes 30-40+
seconds** — something reintroduced a module-level `import sentence_transformers`
(or `torch`) outside `BgeEmbeddingProvider.__init__`. That import must stay
lazy — see "Design notes" for why this exact regression already happened once.

**Tests hang or fail at teardown with "Event loop is closed" (Windows only)** —
a known bad interaction between Windows' default `ProactorEventLoop` and
`asyncpg` when a fixture hands out a live DB connection the test body uses and
then touches again during its own teardown. `tests/conftest.py` works around it
by forcing the `SelectorEventLoop` policy and pinning `loop_scope="function"` on
any fixture that yields a live session (`test_engine`, `session`, `parsing_env`,
`client`). If you add a new fixture in that shape, give it the same treatment.
