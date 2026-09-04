# Checkpoint — Implementation 1 of 3 (Backend + GCP)

**2026-09-05.** The brief is complete. Working tree is green:

```
make lint       All checks passed!
make typecheck  Success: no issues found in 101 source files
make test       358 passed, 1 deselected
make test-all   359 passed          (includes the published FHIR validator)
```

Brief: `MEDIKIOSK_IMPL_1of3_BACKEND_GCP.md` (repository root).
Scope map: `docs/BUILD_BRIEF.md`. Reasoning: `docs/DECISIONS.md`.

**Nothing is committed.** The whole restructure and all three build sessions are
one uncommitted working tree over `b012eb7` — around 200 changed paths.

---

## Where things stand

| § | Area | State |
|---|---|---|
| 3 | Repo restructure into `stale/` | **Done** |
| 4 | Canonical record + versioned input contracts | **Done** |
| 5, 5.1 | Ingest and repair | **Done** |
| 6 | Documents + OCR | **Done** |
| 7 | Report assembly | **Done** |
| 8 | Identity, history, ordering | **Done** |
| 9 | Data + tenancy | **Done** |
| 10 | API, including FHIR validation | **Done** |
| 11 | GCP deployment | **Done** — with one recorded deviation (no MinIO) |
| 12 | Config | **Done** |
| 13 | Tests and definition of done | **14 of 14** |
| 14 | Do-not list | Honoured; each item mapped in `BUILD_BRIEF.md` |

Two deviations from the brief, both argued in `DECISIONS.md` and both listed in
`BUILD_BRIEF.md`: no MinIO in compose (§27), and the evaluation harness shelved
rather than repurposed (§33).

---

## What this session added

### §11 — the deployment

| File | What it is |
|---|---|
| `infra/docker/Dockerfile` | Multi-stage. Builder carries the compiler, runtime does not. Non-root uid 10001. Builds in ~40s, image 259 MB |
| `.dockerignore` | **New, and load-bearing.** Without it the image was 456 MB, 181 MB of which was the developer's own virtualenv, plus `stale/` and local uploads |
| `backend/infra-entrypoint.sh` | `serve` no longer migrates. `migrate` and `seed` stay as explicit subcommands. The `evaluate` subcommand is gone with the harness |
| `docker-compose.yml` | At the repository root. postgres → one-shot migrate → one-shot seed → api, with the worker behind a `worker` profile |
| `infra/gcp/config.sh` | Shared names, and a region check that refuses anything outside `asia-south1`/`asia-south2` |
| `infra/gcp/00-provision.sh` | APIs, three service accounts, Artifact Registry, private services access, Cloud SQL (private IP, no public IP, deletion protection), the bucket, two topics, the secrets, all IAM |
| `infra/gcp/30-build.sh` + `cloudbuild.yaml` | One image, tagged with the git commit rather than `latest` |
| `infra/gcp/35-migrate.sh` | A Cloud Run job that runs `alembic upgrade head` and waits, so a failed migration fails the deploy |
| `infra/gcp/40-deploy.sh` | Both services, the push subscription with dead-lettering, and a post-deploy assertion that the worker route 404s on the public API |
| `infra/gcp/README.md` | How to run all of it, and the one manual step |
| `Makefile` | `make dev`, `make test`, `make deploy`, and the targets they depend on. Finds `backend/.venv` on its own |
| `.env.example` | Rewritten against `Settings`. Every name in it is read by `config.py`; the six that were not are gone |

**Verified, not assumed.** The image was built and its contents inspected; the
compose stack was brought up against real Postgres and driven end to end over
HTTP — ingest, keyless replay, `Idempotency-Key` replay, the Hindi report, an
11-entry FHIR bundle, the worklist, a kiosk denied the worklist (403), and
another hospital denied the intake (404).

### §11 — the missing producer

The Pub/Sub push endpoint existed. **Nothing published to it.** `PubSubBus`
raised `NotImplementedError` from every method, `get_event_bus` never returned
it, and the upload handler always dispatched an in-process background task —
so the cloud worker would have been deployed, wired, IAM'd, and idle forever.

- `app/adapters/queue/dispatch.py` — `InlineDispatcher` and `PubSubDispatcher`
  behind one protocol, selected by `DOCUMENT_QUEUE`, both ending at the same
  `DocumentService.process`. The message carries three ids and nothing clinical.
- `app/api/v1/documents.py` — the upload handler dispatches through it, and
  **awaits** it: a document stored but never queued is one the physician is
  never shown and never told about.
- `tests/adapters/test_dispatch.py` — 12 tests, including one that feeds what the
  dispatcher actually published through `worker._decode`, so producer and
  consumer are checked against each other rather than assumed to agree.
- `EVENT_BUS` and `PubSubBus` deleted. A config switch that appears to offer
  cross-instance fan-out and silently does nothing is worse than not offering it.

### §13.14 — the docs

- `docs/DECISIONS.md` — **rewritten**, 33 entries. The old one described the
  interview-running build: it documented a five-value enum that is not the
  current one, NATS and Redis in compose, and `PubSubBus` as a live placeholder.
- `README.md` — rewritten. The old one advertised 474 tests, an evaluation
  metrics table that does not run, and a compose path that no longer exists.
- `docs/CLINICAL_REVIEW_QUEUE.md` — rewritten by hand against the current
  `clinical/` tree, because its generator moved to `stale/` with the pathway and
  red-flag YAML it read. Now enumerates the 36 Hindi strings, all 20 interaction
  rules with their sources, the 32 ingredient aliases, the 4 flagged concepts,
  the terminology seeds and the consent notice.
- `docs/BUILD_BRIEF.md` — rewritten as a scope map: every brief section to where
  it lives, §13 item by item, and the §14 do-not list mapped to what holds it.
- `infra/gcp/README.md` — new.

---

## The one thing that is open

**`DECISIONS.md` §31 — Vertex ML processing residency.**

`app/adapters/ocr/gemini.py` and `app/adapters/llm/vertex.py` both refuse to
construct unless `VERTEX_REGION` is Indian **and** `VERTEX_ZDR_ENABLED` is true.
Those guards are real and tested. What nobody has verified and written down is
whether ML *processing* — as distinct from storage at rest — stays in region for
the specific model configured.

Somebody with access to the project's terms has to confirm, for the exact model
id: that inference runs in region, that ZDR applies to it, and that neither
changes when the model versions up. The finding goes in `DECISIONS.md` with a
date and a source.

**This is a decision for the team, not for the agent.** The guards fail closed,
so shipping without the answer is impossible rather than merely unwise — but it
also means `OCR_PROVIDER=gemini` cannot be switched on until somebody answers.

---

## Defects found and fixed across this build

Eleven, all surfaced by writing tests, running `mypy` for the first time, or
actually running the deployment artefacts rather than reading them.

| # | Defect | Found by |
|---|---|---|
| 1 | The tenancy guard raised `AttributeError` instead of `MissingTenantFilter` on UPDATE and DELETE — refused, but for a reason nobody would read as a tenancy problem | writing `test_tenancy.py` |
| 2 | The FHIR bundle was not valid R4: underscores in every `id`, `urn:uuid:` on non-UUIDs. The validator rejected every resource | the network test |
| 3 | `DocumentService.process` was not idempotent; a Pub/Sub redelivery duplicated every extracted line | `test_worker.py` |
| 4 | **Nothing published to the Pub/Sub topic.** The cloud worker had no producer | writing the deploy script |
| 5 | The image shipped the developer's 181 MB virtualenv and `stale/` | building it |
| 6 | Two terminology endpoints raised on every call — builders called with an old signature | `mypy` |
| 7 | A kiosk retry with no `Idempotency-Key` was a 500 | `test_idempotency.py` |
| 8 | `WorklistEntry.contradiction_count` was hardcoded to zero, so a conflict-only intake rendered `ready` | `test_worklist.py` |
| 9 | A kiosk token naming an unseeded hospital gave a bare `Internal Server Error` | running compose |
| 10 | `µg/L` vs `ug/L` read as a unit mismatch; `"Tab. Metformin 500 BD"` resolved to nothing | `test_labs.py`, `test_medicines.py` |
| 11 | `backend/evaluation/` had not imported since the restructure | running it |

---

## Notes for whoever picks this up

- **Nothing is committed.** One working tree over `b012eb7`.
- `make test` and friends find `backend/.venv` themselves; no activation needed.
- The goldens in `tests/report/golden/` fail on first write by design — write the
  file, read the diff, then accept it. One line in each changed this build,
  because prescription lines now resolve where they previously did not.
- `tests/api/test_worker.py` must patch **both** `config_module.get_settings` and
  `app.main.get_settings`, because `main.py` imports the function directly.
- `KIOSK_TOKENS` must name a hospital the seeder created (`aiia-delhi`).
- Compose interpolates every service's variables regardless of profile, so
  `PUBSUB_PUSH_TOKEN` cannot be a `:?` required variable without breaking the
  default demo stack.

## What is genuinely not built

Listed with reasons in `DECISIONS.md` §33: staff authentication beyond the
header stand-in, kiosk token rotation, pushing the FHIR bundle into an HMIS, an
S3-compatible object store, and multi-instance dashboard fan-out.
