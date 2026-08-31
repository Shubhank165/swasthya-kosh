# Build brief

The original handoff brief for this build is kept at the repository root as
`MEDIKIOSK_BACKEND_BUILD_PROMPT.md`. This file records what was built against
it, so a reviewer can check scope without reading both.

## Delivered

| Brief section | Where |
|---|---|
| 5. Clinical domain model | `backend/app/domain/clinical/` |
| 6. Clinical state machine | `backend/app/domain/statemachine/`, `clinical/pathways/` |
| 7. Red-flag engine | `backend/app/domain/redflags/`, `clinical/redflags/` (24 rules) |
| 8. Coverage, contradictions, summary | `backend/app/domain/{coverage,contradictions,summary}/` |
| 9. Queue domain | `backend/app/domain/queue/`, `backend/app/services/queue.py` |
| 10. Terminology module | `backend/app/domain/ontology/matching.py`, `backend/app/services/terminology.py` |
| 11. Persistence, events, API | `backend/app/{models,repositories,events,api}/` |
| 12. Evaluation harness | `backend/evaluation/` (22 scenarios) |
| 13. Security and privacy | `backend/app/core/logging.py`, `backend/app/api/deps.py`, `clinical/consent/` |

## Definition of done

| # | Item | Status |
|---|---|---|
| 1 | `docker compose up` works; `alembic upgrade head` from empty | Compose stack in `infra/compose/`; migrations verified up and down |
| 2 | Seeded AYUSH facility, 3+ concurrent queues, all 3 assignment policies | 8 departments, 8 queues, 4 opened; asserted in `tests/api/test_queue_api.py::TestSeededFacility` |
| 3 | End-to-end integration test asserting report content | `tests/integration/test_end_to_end.py::TestFullIntakeJourney` |
| 4 | `mypy --strict` clean on `app/domain/**`; `ruff` clean everywhere | Both clean |
| 5 | Domain coverage above 90% | 94% |
| 6 | Every red-flag rule has a positive and a negative test | 24 rules, 48 cases, enforced by a test that fails if a rule has neither |
| 7 | Concurrency test proves `call_next` never double-issues | `tests/integration/test_concurrency.py`, against real Postgres |
| 8 | Idempotency test proves a replay does not duplicate | `tests/api/test_intake_api.py::TestIdempotency` |
| 9 | `python -m evaluation.run` prints metrics, exits non-zero on an unsupported assertion | Verified; also run inside pytest |
| 10 | `README.md` and `docs/DECISIONS.md` | Both written |

## Out of scope, as specified

Vertex AI / Sarvam / OpenAI calls; Jetson and Raspberry Pi edge profiles;
frontend applications; live ABDM, A-HMIS and FHIR credentials. Adapter
interfaces and deterministic mocks exist for all of them and run in CI.

## Design targets kept open

- **Realtime voice profile.** `QuestionRenderer` receives a `Step` the state
  machine already chose, and returns one authored question string per turn. A
  voice renderer slots in as an implementation of that protocol.
- **Async document-OCR worker.** `IntakeService.apply_document_extraction` is
  the entry point; the upload endpoint calls it inline today and a worker would
  call the same method.
- **`SHADOW` deployment mode.** `QUEUE_MODE=shadow` makes MediKiosk own only
  `IntakeState`; `require_shadow_mode_guard` rejects queue mutations the HMIS
  owns, and `HISAdapter` supplies encounters and tokens.
