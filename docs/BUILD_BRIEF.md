# Build brief — scope map

The brief for this build is `MEDIKIOSK_IMPL_1of3_BACKEND_GCP.md` at the
repository root: *Implementation 1 of 3 (Backend + GCP)*. This file records
what was built against each section, so a reviewer can check scope without
reading both documents side by side.

Current state against the definition of done is in `docs/CHECKPOINT_IMPL_1.md`.
Reasoning for the choices is in `docs/DECISIONS.md`.

## Delivered

| § | Brief section | Where |
|---|---|---|
| 3 | Restructure: keep, shelve | `backend/stale/` + `backend/stale/README.md` |
| 4 | Canonical record, versioned contracts | `app/domain/record.py`, `app/normalize/` |
| 4.2 | Unsupported schema version is a named error | `app/normalize/registry.py` |
| 5 | Ingest | `app/services/ingest.py` |
| 5.1 | Repair, and never dropping a payload | `app/services/repair.py`, `app/repositories/consent.py` (`ingest_raw`) |
| 6 | Documents and OCR | `app/services/documents.py`, `app/domain/documents/`, `app/adapters/ocr/` |
| 6.2 | Residency and ZDR guards | `app/adapters/ocr/gemini.py`, `app/adapters/llm/vertex.py` — **and an open question, `DECISIONS.md` §31** |
| 7 | Report assembly and verification | `app/domain/report/`, `app/services/reports.py`, `clinical/report_templates/` |
| 8 | Identity, history, ordering | `app/services/identity.py`, `app/services/worklist.py`, `app/adapters/abha/` |
| 9 | Data model and tenancy | `app/models/`, `app/repositories/`, `app/db/tenancy.py` |
| 10 | API, including FHIR R4 export | `app/api/v1/`, `app/adapters/fhir/mapper.py` |
| 11 | GCP deployment | `infra/docker/`, `docker-compose.yml`, `infra/gcp/`, `Makefile` |
| 12 | Config | `app/core/config.py`, `.env.example` |
| 13 | Tests and definition of done | `backend/tests/` — 358 offline, 1 network |
| 14 | Do-not list | Honoured; see below |

## §13, item by item

| # | Item | Where |
|---|---|---|
| 1 | `docker compose up` then `alembic upgrade head` from empty gives a working stack | `tests/integration/test_migration.py`, and verified by running it |
| 2 | A seeded hospital with departments and intakes | `app/services/seed.py`; `test_migration.py::TestSeedingTheMigratedDatabase` |
| 3 | End-to-end: ingest → document → contradiction → report → FHIR | `tests/integration/test_end_to_end.py` |
| 4 | Normalizer contract test per schema version, golden fixtures | `tests/contracts/test_normalizer_registry.py` |
| 5 | Repair test; unrepairable payloads stored and flagged | `tests/safety/test_repair.py` |
| 6 | Status vocabulary survives ingest → storage → report | `tests/safety/test_status_vocabulary.py` |
| 7 | Idempotency — the same ingest twice is one intake | `tests/api/test_idempotency.py` |
| 8 | A query without a hospital filter fails | `tests/safety/test_tenancy.py` |
| 9 | Every route asserted against its required role, from OpenAPI | `tests/api/test_roles.py` |
| 10 | Aadhaar-shaped numbers never reach the database or a log | `tests/safety/test_redaction.py` |
| 11 | Clinical text cannot reach a log record | `tests/safety/test_logging_phi.py` |
| 12 | Report determinism, byte-identical goldens | `tests/report/test_determinism.py` |
| 13 | `mypy --strict` on domain and normalize; `ruff` clean | `make check` |
| 14 | `README.md` and `docs/DECISIONS.md`, including the Vertex finding | This build; the finding is recorded as **open** — `DECISIONS.md` §31 |

## §14 — the do-not list, and how each is held

| Do not | How |
|---|---|
| Implement a state machine, question selection or red-flag evaluation | None exists; the previous build's is in `stale/`. Red flags arrive as already-fired events and are persisted, not re-evaluated |
| Let a model decide anything clinical | The only model in the clinical path is repair, which is optional (`REPAIR_PROVIDER=none`) and marks every field it touched |
| Collapse the five statuses | `tests/safety/test_status_vocabulary.py`, and the FHIR exhaustiveness assertion in `tests/adapters/test_fhir.py` |
| Increase certainty silently | `CertaintyIncreaseError`; only physician verification may, and it records who |
| Invent a terminology code | The mapper emits text with no coding where no mapping exists; `tests/adapters/test_fhir.py` asserts it |
| Put a secret, key, model id or hostname in the repository | Everything is `Settings`; `.env.example` has no values; compose refuses to start without the two credentials |
| Log clinical text | The PHI filter, with `tests/safety/test_logging_phi.py` |

## Deviations from the brief

Two, both argued in `docs/DECISIONS.md`:

- **No MinIO in `docker-compose.yml`** (§11 lists it). There is no
  S3-compatible object store in the codebase, so the container would be wired to
  nothing. `DECISIONS.md` §27 says what building one would take.
- **`backend/evaluation/` is shelved rather than repurposed** (§3 says
  "repurposed in §13"). Its function in §13 is discharged by the fourteen test
  items above, all passing. `backend/stale/README.md` says why, and what
  reviving it would mean.
