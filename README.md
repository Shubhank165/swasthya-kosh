# MediKiosk — backend core and clinical engine

Ayurveda-first pre-consultation clinical intake for Indian AYUSH hospital OPDs.
SIH 2026, PS 26047, Ministry of Ayush / All India Institute of Ayurveda.

MediKiosk collects a patient's medical history during their waiting time — by
voice, by touch, and by scanning their old prescriptions and lab reports — and
hands the physician a structured, evidence-linked, physician-verifiable history
before the patient walks into the consultation room.

**This is not a diagnostic system.** It never states a diagnosis, never gives
medical advice, and never tells a patient what is wrong with them. Its output is
always a draft intake requiring physician verification.

## What this build contains

The deterministic core. **No model calls anywhere.** Every clinical behaviour
here is correct, testable and explainable without any AI in the loop. Cloud
providers plug in behind protocols in `app/adapters/protocols.py`, and nothing
above that package changes when they do.

| | |
|---|---|
| Domain core | `backend/app/domain/**` — pure, no framework, no I/O, no clock |
| Clinical content | `clinical/**` — YAML a Vaidya can review in a pull request |
| Persistence | Postgres via SQLAlchemy 2.0 async, Alembic from the first commit |
| API | FastAPI, `/api/v1`, plus two WebSocket channels |
| Providers | Protocols for STT, TTS, extraction, OCR, HIS, FHIR, ABDM — mocks only |
| Evaluation | 22-scenario replay harness reporting clinical-safety metrics |
| Tests | 457 tests; 94% coverage on the domain |

## Quick start

### With Docker

```bash
cp .env.example .env          # then set POSTGRES_PASSWORD and MINIO_ROOT_PASSWORD
docker compose -f infra/compose/docker-compose.yml up --build
curl localhost:8000/health
```

The API container runs `alembic upgrade head` and seeds the demo facility on
start, so a cold machine comes up ready. The compose file is also the on-prem
deployment story — the same file a hospital runs on a box in its records room.

### Locally

```bash
cd backend
uv venv && uv pip install -e ".[dev]"

export DATABASE_URL="postgresql+asyncpg://medikiosk:<password>@localhost:5432/medikiosk"
uv run alembic upgrade head
uv run python scripts/seed.py
uv run uvicorn app.main:app --reload
```

Open <http://localhost:8000/docs>.

## Running the checks

```bash
cd backend

uv run pytest                       # 457 tests
uv run pytest --cov=app.domain      # domain coverage (94%)
uv run ruff check app tests evaluation scripts
uv run mypy --strict app/domain

uv run python -m evaluation.run     # the clinical metrics table
```

The concurrency suite needs real Postgres, because `SELECT … FOR UPDATE SKIP
LOCKED` does not exist on SQLite. It skips with an explanation unless you point
it at one:

```bash
docker run -d --name pg -e POSTGRES_PASSWORD=<password> -e POSTGRES_USER=medikiosk \
  -e POSTGRES_DB=medikiosk_test -p 55432:5432 postgres:16-alpine

TEST_DATABASE_URL="postgresql+asyncpg://medikiosk:<password>@localhost:55432/medikiosk_test" \
  uv run pytest tests/integration
```

## The evaluation harness

`python -m evaluation.run` drives 22 synthetic patients through the real state
machine with mock providers and reports what happened. It exits non-zero on any
unsupported assertion, so a clinical-safety regression fails the build like a
broken unit test.

```
MediKiosk clinical evaluation
========================================================
scenarios run                             22
scenarios passed                       22/22  all
required-field recall                 100.0%  100%
missing-field rate                      3.4%  low
irrelevant questions / session          0.00  0.00
red-flag recall                       100.0%  100%
red-flag false-positive rate            0.0%  0%
unsupported-assertion rate              0.00  0.00 (hard)
questions to completion (mean)          59.1
completion rate                        95.5%
mean coverage                          96.0%
========================================================
```

`--json` for machine-readable output, `--report <scenario_id>` to print the
generated physician report for one scenario and read it yourself.

## The clinical content

Everything a clinician might want to change lives in `clinical/` as YAML, not in
Python. A Vaidya reviews a pull request against these files without reading any
code.

```
clinical/
  pathways/            core_intake.yaml + one file per presenting complaint
    screens/           red-flag screens, per complaint plus a default
    ros/               review-of-systems groups
  redflags/            24 rules, each naming who approved it
  ayurveda/            patient-reportable Ayurveda module
  terminology/         concept registry, NAMASTE / ICD-11 seeds, ConceptMap
  consent/             versioned consent notice and purpose codes
```

Content is validated strictly at startup. A pathway that does not parse, or a
red-flag rule reading a concept no screen ever asks, stops the process — a
system that quietly asks fewer safety questions than it was configured to is
the failure mode worth refusing to boot over.

`docs/CLINICAL_REVIEW_QUEUE.md` is generated from the content itself
(`scripts/review_queue.py`) and lists everything an engineer authored without a
clinician. It is the agenda for the AIIA mentor session.

## Architecture in one paragraph

The **clinical state machine** decides what is asked, in what order, and when the
history is complete. It is a pure function of the fact set plus the YAML content:
no randomness, no clock, no model. A generative renderer may later re-word a
question; it never chooses one. **Red-flag evaluation** is a separate pure
function over the same facts, and it emits an alert for a human to acknowledge —
there is no code path from a fired rule to a queue mutation, and a test asserts
that the red-flag package imports nothing from the queue package. Every
**clinical fact** is immutable and carries its full provenance, so a line of the
generated report links back to the transcript offset or the region of the scan it
came from.

See `docs/DECISIONS.md` for every architectural choice and its reasoning.

## API surface

```
POST   /api/v1/intakes                              create a session
GET    /api/v1/intakes/{id}
PATCH  /api/v1/intakes/{id}                         session metadata only
POST   /api/v1/intakes/{id}/answers                 one answer -> state + next question
GET    /api/v1/intakes/{id}/next-step
GET    /api/v1/intakes/{id}/coverage
POST   /api/v1/intakes/{id}/documents               upload a scan
POST   /api/v1/intakes/{id}/confirm                 patient confirmation loop
GET    /api/v1/intakes/{id}/report
GET    /api/v1/intakes/{id}/facts/{fact_id}/evidence

POST   /api/v1/consent                              record a consent artefact
GET    /api/v1/consent/{id}

GET    /api/v1/departments
GET    /api/v1/queues                               ?department=
GET    /api/v1/queues/{id}/instance                 ?date= &session=
POST   /api/v1/queues/{id}/tickets                  issue
POST   /api/v1/tickets/{id}/{call|recall|start|complete|defer|transfer|no-show|cancel|escalate}
POST   /api/v1/queue-instances/{id}/{call-next|pause|resume|close}
GET    /api/v1/queue-instances/{id}/dashboard

GET    /api/v1/terminology/search                   ?q= &systems=
GET    /api/v1/terminology/{CodeSystem|ConceptMap|ValueSet}
POST   /api/v1/physician/{intake_id}/verify         physician-only
POST   /api/v1/alerts/{id}/{acknowledge|dismiss}

WS     /ws/dashboard?department=                    queue + intake + alert fanout
WS     /ws/intakes/{id}                             live intake state for the kiosk
```

Every mutating endpoint accepts an `Idempotency-Key`, and every intake carries a
monotonic `revision` — a kiosk that lost the LAN and retries neither duplicates
nor clobbers.

## Configuration

All configuration is environment-driven; see `backend/app/core/config.py` and
`.env.example`. **There is no secret, key, model id or hostname literal anywhere
in this repository, including in fixtures.** The compose file refuses to start
rather than booting with a default password.

Two settings worth knowing about:

- `QUEUE_MODE` — `source_of_truth` (MediKiosk owns the queue) or `shadow` (a
  hospital HMIS owns encounters and tokens; MediKiosk owns only intake state).
- `PREFER_INTAKE_READY` — off by default. See `docs/DECISIONS.md`.

## Not in this build

Vertex AI, Sarvam and OpenAI calls; Jetson and Raspberry Pi edge profiles;
frontend applications; live ABDM, A-HMIS and FHIR credentials. The adapter
interfaces and mock implementations for all of these exist and are exercised in
CI.

## Safety properties, and where they are proven

| Property | Proof |
|---|---|
| No model decides what is asked or whether history is complete | `tests/safety/test_no_auto_escalation.py::TestNoModelInTheLoop` |
| A red flag never auto-escalates a patient | `tests/safety/test_no_auto_escalation.py` |
| Every red-flag rule has a positive and a negative case | `tests/safety/test_redflag_rules.py` (48 cases over 24 rules) |
| Logs never contain clinical text | `tests/safety/test_logging_phi.py` |
| No prompt or report gives advice or a diagnosis | `tests/safety/test_content_integrity.py` |
| The five-value status is never collapsed to a boolean | `tests/unit/test_clinical_fact.py::TestFiveValueStatus` |
| Certainty is never silently increased | `tests/unit/test_clinical_fact.py::TestCertaintyNeverIncreases` |
| The original expression survives normalisation | `tests/unit/test_clinical_fact.py::TestOriginalExpressionSurvives` |
| `call_next` never double-issues a token | `tests/integration/test_concurrency.py` (Postgres) |
| A replayed offline submission does not duplicate | `tests/api/test_intake_api.py::TestIdempotency` |
| No residual state after a kiosk session ends | `tests/integration/test_concurrency.py::TestSessionTeardown` |

## Licence and data

No credentials, no real patient data, and no Tailscale or SSH details are in this
repository. The terminology seeds are development placeholders shaped like real
NAMASTE and ICD-11 codes; they must be replaced with the licensed releases before
any clinical use, and `docs/CLINICAL_REVIEW_QUEUE.md` says so.
