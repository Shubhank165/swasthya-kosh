# MediKiosk — clinical intake for AYUSH OPDs

Ayurveda-first pre-consultation clinical intake for Indian AYUSH hospital OPDs.
SIH 2026, PS 26047, Ministry of Ayush / All India Institute of Ayurveda.

A patient waiting for an OPD appointment answers questions at a kiosk and
photographs their old prescriptions and lab reports. This service receives that
interview, reads the documents, reconciles the two, and hands the physician a
structured, evidence-linked history before the patient walks into the room.

**This is not a diagnostic system.** It never states a diagnosis, never gives
medical advice, and never tells a patient what is wrong with them. Its output is
a draft intake awaiting physician verification, and every rendered report says so
in its first line.

**The backend does not run the interview.** Question selection, red-flag
evaluation and turn logic live on the Jetson at the kiosk. This service receives
results. There is no state machine here, and adding one would be a mistake — the
previous build's is in `backend/stale/` with a note explaining why it moved.

---

## Quick start

The whole system on a laptop, with no Google account and no network. This is
also the demo path if venue wifi fails.

```bash
cp .env.example .env     # set POSTGRES_PASSWORD and KIOSK_TOKENS; nothing else is required
make dev
```

Compose brings up Postgres, runs the migrations as their own one-shot service,
seeds the demo facility, starts the API, and then serves the doctor's dashboard
beside it — in that order, each waiting on the last.

```bash
open  localhost:5173           # the dashboard: worklist, report, evidence
curl  localhost:8000/readyz    # says which providers are live and which shape this is
open  localhost:8000/docs
```

The dashboard proxies `/api` and `/ws` to the API, so the page, the API and the
socket are one origin — the same shape the deployment has. Nothing in this stack
needs a Google account or a network.

`KIOSK_TOKENS` is a JSON object mapping each kiosk's token to its hospital:
`{"<token>":"aiia-delhi"}`. `aiia-delhi` is the id the seeder creates. There is
no default token and no default password anywhere in this repository; compose
refuses to start rather than booting with a credential that is written down in a
public repo.

### Without Docker

```bash
cd backend
uv venv && uv pip install -e ".[dev]"
export DATABASE_URL="postgresql+asyncpg://medikiosk:<password>@localhost:5432/medikiosk"
make migrate && make seed
uv run uvicorn app.main:app --reload
```

### Deploying to GCP

```bash
export PROJECT_ID=your-project
make provision    # idempotent; safe to re-run after it fails partway
make deploy       # check → build → migrate → deploy, in that order
```

That deploys with the mock providers, which is the default and stays the
default: a deployment that reaches a model without anybody typing so is a
deployment nobody decided to make. To run the real ones, name them and the
models, and assert the residency claim:

```bash
OCR_PROVIDER=gemini    OCR_MODEL_ID=<model> \
REPAIR_PROVIDER=vertex REPAIR_MODEL_ID=<model> \
VERTEX_ZDR_ENABLED=true \
make deploy
```

The model ids are not in this repository and are refused if missing.

To drive the **app** against a deployment, add `DEPLOY_ENVIRONMENT=staging`. The
only thing in the backend that reads the environment is `PatientAuthService`,
which returns the six-digit OTP in the sign-in response when the sender is the
mock and the environment is not production — without it there is no SMS gateway
and no code, so sign-in cannot complete. With it, anyone who knows a phone
number can sign in as that patient, so it belongs on a deployment holding no
real records and nowhere else. The deploy prints that back at you.
`VERTEX_ZDR_ENABLED` is refused if a cloud provider is selected without it, in
`infra/gcp/config.sh`, before an image is built — and setting it is an assertion
you are making about the project, which nothing here can verify. Read the
section below first.

`infra/gcp/README.md` has the detail, including the one manual step (the kiosk
tokens secret) and the residency question that must be answered before any
cloud model is switched on.

---

## What it does

**Ingest.** A versioned kiosk payload becomes a `CanonicalRecord`. A payload that
fails validation is repaired if repair is enabled, and stored raw and flagged if
it cannot be — never dropped. A retry is a retry whether or not the device sent
an `Idempotency-Key`, because the kiosk's own `intake_id` already identifies the
interview.

**Documents.** A photographed prescription or lab report is stored, read, and
turned into facts that sit *beside* what the patient said rather than replacing
it. Medication names are aligned through an ingredient index, so a spoken
"Metformin" and a printed "Tab. Metformin 900.2 mg BD" compare on the same field
and the dose discrepancy is what gets reported. Lab values are classified only
against the range printed on the same document.

**The report.** Assembled from reviewed per-language templates — never
machine-translated at request time — and rendered in the patient's own language
by default. Contradictions are recomputed on every read, so a document arriving
an hour after the interview changes what conflicts without anything being
re-ingested.

**Export.** `GET /api/v1/fhir/intakes/{id}` returns a dual-coded R4 Bundle that
validates against the published HAPI validator with zero errors, is byte-stable
between identical requests, and never invents a code it was not given.

## What it refuses to do

These are the properties worth arguing about, so each one names the test that
holds it.

| Property | Held by |
|---|---|
| Five statuses — `answered`, `unresolved`, `not_asked`, `not_applicable`, `refused` — survive ingest, storage, the report and FHIR without two ever collapsing into one, and none renders as "no" | `tests/safety/test_status_vocabulary.py` |
| Certainty never increases, except by physician verification, which records who | `Fact.revise` raises `CertaintyIncreaseError`; `tests/report/` |
| A database query without a hospital filter raises rather than returning another hospital's rows — on SELECT, UPDATE and DELETE | `tests/safety/test_tenancy.py` |
| An Aadhaar-shaped number in OCR output never reaches the database or a log | `tests/safety/test_redaction.py` |
| Clinical text cannot reach a log record | `tests/safety/test_logging_phi.py` |
| A malformed payload is stored and flagged, and every repaired field is marked | `tests/safety/test_repair.py` |
| The same ingest replayed produces one intake, with or without a key | `tests/api/test_idempotency.py` |
| Every route's required role, enumerated from the OpenAPI schema | `tests/api/test_roles.py` |
| The report is byte-identical to its golden file | `tests/report/test_determinism.py` |
| A document redelivered by Pub/Sub does not duplicate its extracted lines | `tests/api/test_worker.py` |
| The queue message carries identifiers and nothing clinical | `tests/adapters/test_dispatch.py` |

## Checks

```bash
make check        # ruff, mypy, and the offline suite — what `make deploy` runs first
make test         # 483 tests, no network
make test-all     # + the FHIR bundle against the published HAPI validator
```

The other two parts, each with a suite that runs against a real backend rather
than a stub:

```bash
cd dashboard && npm test && npm run typecheck && npm run lint
cd dashboard && npm run e2e            # Playwright; starts its own backend
cd app       && flutter test           # 158 tests
cd app       && flutter test test/live_backend_test.dart \
                  --dart-define=MEDIKIOSK_LIVE=http://localhost:8000
cd app       && flutter test integration_test/journey_test.dart -d <device>
```

The last two are the ones worth running before a demo. Each of them, the first
time it was run, found something no unit test could — see
`docs/CHECKPOINT_IMPL_3.md`.

`mypy` is strict on `app.domain.*`, `app.normalize.*` and `app.contracts.*` — the
parts a schema change touches and where a silent `None` is a clinical error — and
ordinary elsewhere.

---

## Layout

```
backend/app/
  domain/          pure: no framework, no I/O, no clock, no id generator
    record.py        CanonicalRecord, Fact, FieldStatus, Certainty
    documents/       extraction, medicines, labs, alignment, interactions
    contradictions/  voice facts against document facts
    report/          template assembly and text rendering
  normalize/       versioned kiosk payload -> CanonicalRecord
  services/        the I/O around the domain
  repositories/    SQLAlchemy, all tenant-scoped
  adapters/        OCR, repair, storage, ABHA, FHIR, the document queue
  api/v1/          FastAPI routers
  db/tenancy.py    the guard that raises on an unscoped query
backend/stale/     the previous build. Kept, not maintained, not deployed.
clinical/          YAML a clinician can review in a pull request
infra/             Dockerfiles, cloudbuild, gcloud scripts

app/               the patient's phone (Flutter). Touch, plus optional voice —
                   read-aloud and speech input both run on the device; no audio
                   is stored or sent (DECISIONS §68).
dashboard/         the doctor's screen (React). Renders; never computes.
```

`clinical/` holds the report templates and field labels per language, the
terminology seeds and ConceptMap, the drug-interaction table with a citation per
row, and the versioned consent notice. It is validated at startup and shipped
inside the image, so a deployed build and the content it renders cannot drift
apart.

## API

```
POST   /api/v1/intakes/ingest                       one completed kiosk interview
GET    /api/v1/intakes/{id}
GET    /api/v1/intakes/{id}/report                  ?language=
POST   /api/v1/intakes/{id}/verify                  physician-only
POST   /api/v1/intakes/{id}/facts/{fact_id}/verify  physician-only: accept/amend/reject
GET    /api/v1/intakes/{id}/facts/{fact_id}/evidence
POST   /api/v1/intakes/{id}/documents               upload a scan
GET    /api/v1/intakes/{id}/documents
POST   /api/v1/intakes/{id}/documents/results       results produced on the device
GET    /api/v1/documents/content/{key}
GET    /api/v1/fhir/intakes/{id}                    dual-coded R4 Bundle
GET    /api/v1/worklist                             ?department= &state=  no clinical text
POST   /api/v1/patients/resolve
GET    /api/v1/patients/{ref}/history
POST   /api/v1/consent  ·  GET /api/v1/consent/{id}
GET    /api/v1/terminology/{search,dual-codes,CodeSystem,ConceptMap,ValueSet}
GET    /api/v1/alerts                               ?acknowledged=  unacknowledged first
POST   /api/v1/alerts/{intake_id}/acknowledge
GET    /api/v1/metrics/ingest
GET    /api/v1/metrics/correction-rate              admin-only
GET    /healthz  ·  /readyz
WS     /ws/...                                      dashboard fan-out
```

Not listed, and deliberately: `POST /api/v1/worker/documents`. It is the Pub/Sub
push endpoint and it is registered only where `PUBSUB_PUSH_ENABLED` is set, so it
does not exist on the public API at all. The deploy script fails if it ever
answers anything but 404 there.

Every mutating endpoint accepts `Idempotency-Key`, enforced by a test that walks
the generated OpenAPI schema.

## Configuration

Environment-driven, defined in one place (`backend/app/core/config.py`) and
documented in `.env.example`. **There is no secret, key, model id or hostname
literal anywhere in this repository, including in fixtures.**

The four settings that decide what a deployment actually is:

| | Local | Cloud |
|---|---|---|
| `OCR_PROVIDER` | `mock` — cached results for the fixture documents | `gemini` (see the residency question below) |
| `REPAIR_PROVIDER` | `mock` | `vertex`, or `none` to keep models away from patient input entirely |
| `STORAGE_BACKEND` | `local` | `gcs` |
| `DOCUMENT_QUEUE` | `inline` — a background task, no broker | `pubsub` — a separate Cloud Run worker |

Both queue paths end at the same `DocumentService.process`, so the laptop demo
and the cloud deployment cannot produce different records from the same
photograph.

## Before switching on cloud models

`OCR_PROVIDER=gemini` and `REPAIR_PROVIDER=vertex` refuse to construct unless
`VERTEX_REGION` is Indian and `VERTEX_ZDR_ENABLED` is true. Those guards are
real, but they do not establish that **ML processing** — as opposed to storage at
rest — stays in region for the model in use.

**That question is open and has to be answered in writing before either provider
is enabled anywhere near real patient data.** It is decision 31 in
`docs/DECISIONS.md`, and it is a decision for the team.

The demo deployment runs both providers anyway, deliberately, on a project
holding synthetic documents and no patient record. That is a defensible posture
for a demo and not one for a hospital, and the difference is the sentence above,
not a flag.

`backend/scripts/smoke_vertex.py` drives both adapters against a real project by
hand. `make check` does not run it and CI has no credentials for it — which is
why it is worth running: the two calls it took to get working found a document
that would have dead-lettered on a printed date, and a repair that invented the
record's `intake_id`. Decisions 66 and 67.

## What can and cannot be claimed

Worth having in the README rather than only in a slide deck, because the
temptation to round these up is strongest ten minutes before a demo.

**Can:**

- Two intake paths — the Jetson kiosk and the patient's phone — produce the same
  record. The backend normalises it, repairs it if malformed, reads the
  documents, and renders a template-based report a physician verifies fact by
  fact.
- A whole intake has gone from the app's own code into a running backend and
  come back accepted, including a photographed prescription through the real
  multipart endpoint.
- The eleven-screen app sequence passes on a physical Android device.
- `docker compose up` produces the entire system offline.

**Cannot:**

- **"Nine languages."** Questions exist in nine; the consent notice is English
  and Hindi only, so seven of the nine stop at the consent screen. That is the
  correct failure — proceeding without consent would be worse — but the honest
  claim is *"questions in nine languages, consent in two"* until a native speaker
  translates the notice.
- **The old evaluation figures.** 100% required-field recall, 100% red-flag
  recall, zero unsupported assertions: those came from a harness that tested
  question selection, which now runs on the Jetson, so they describe nothing this
  backend does. The harness is in `backend/stale/`. The replacements are
  **repair rate**, **completion rate** and **correction rate**, all three live and
  all three reproducible. The correction rate reports `null` rather than `0.0`
  until a physician has reviewed something — a zero on an empty denominator reads
  as "never wrong".
- **iOS.** Unverified, and it stays that way without a Mac. Android-only is a
  reasonable scope statement; implying iOS works is not.
- **Cloud document reading.** The Vertex processing region is unconfirmed, so the
  adapters fail closed. It does not block the kiosk path — the Jetson reads
  documents on-device and sends results up, so no image leaves the building — and
  blocks only documents uploaded from the phone.
- **Clinical sign-off.** Every red-flag rule carries `clinical_source: pending`.
  See `docs/CLINICAL_REVIEW_QUEUE.md`.

## Not in this build

The Jetson and Raspberry Pi edge profiles; live ABDM, A-HMIS and FHIR
credentials; an S3-compatible object store; pushing the FHIR bundle into a
hospital HMIS; queue management, which the hospital's own HMIS already does.
`docs/DECISIONS.md` §27 and §33 say why for each, and what it would take.

## Reading further

- `docs/DECISIONS.md` — every choice, and the option it closed off
- `docs/CHECKPOINT_IMPL_1.md` · `_2` · `_3` — build state against each brief
- `infra/gcp/README.md` — deployment
- `backend/stale/README.md` — what the previous build was and why each piece moved

## Data

No credentials, no real patient data. The terminology seeds are development
placeholders shaped like real NAMASTE and ICD-11 codes and must be replaced with
the licensed releases before clinical use; the Hindi templates and the
interaction table are engineer-authored and await clinician review.
`docs/CLINICAL_REVIEW_QUEUE.md` and `docs/DECISIONS.md` §32 list them.
