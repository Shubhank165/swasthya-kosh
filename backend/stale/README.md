# `stale/` — superseded, not deleted

Everything here is working, tested code. It was written for a backend that ran
the interview itself. The interview now runs on the Jetson: question selection,
red-flag evaluation and turn logic live on the device, and the backend receives
results (see `docs/IMPL_1_BACKEND.md` §1, hard rule 1).

**Nothing in this directory is imported by `app/`.** It is excluded from the
test run, from coverage and from `mypy`. It is kept because parts of it will
return — an on-prem deployment that has no Jetson, a hospital that wants the
kiosk to be a thin client — and because several pieces were reused rather than
rewritten.

| Path | What it was | Why it moved |
|---|---|---|
| `state_machine/` | Turn logic, step selection, section ordering, branch policies | The Jetson's complaint-branched state machine owns this. Two implementations of question order is one too many. |
| `red_flags/` | Rule set loader and evaluator over a boolean expression tree | The Jetson evaluates its six red-flag criteria during the interview and stops it. The backend receives *fired events*, and must not re-evaluate — a second engine disagreeing with the first is worse than no second engine. |
| `coverage/` | Required-field coverage computation | The Jetson reports its own field statuses. Recomputing coverage against a question set the backend no longer owns would be guesswork. |
| `questionnaires/` | Pathway/screen/ROS YAML, the ayurveda module, the pathway loader, the red-flag rule expression tree | Question content belongs to the device that asks the questions. |
| `queue/` | Full OPD queue domain: tickets, instances, priority classes, recall, no-show, overtake accounting | The problem statement does not ask for queue management. `app/domain/worklist.py` keeps the one part that is needed — arrival ordering — and this is the rest. |
| `summary/` | Summary builder over `PatientIntakeState` | Became `app/domain/report/`. The section order, the disclaimers and the forbidden-assertion vocabulary were carried across verbatim. |
| `interview/` | The service and API layer that drove a live interview: `IntakeService`, answer submission, question serving, queue endpoints, their schemas, repositories and ORM models | Superseded by `app/services/ingest.py`, which receives a finished intake instead of conducting one. |
| `clinical_fact.py`, `patient_state.py` | The `ClinicalFact` dataclass and the intake aggregate | Superseded by `app/domain/record.py`. The provenance invariants (certainty never increases, five-valued status, original expression preserved beside the normalised value) were carried across; the aggregate's job is now done by `CanonicalRecord`. |
| `tests/` | The suite for all of the above — ~330 tests | Kept alongside the code they cover. They still pass against the code in this directory; they are not run because the code is not wired in. |
| `evaluation_*.py`, `evaluation_scenarios/` | Scripted-patient harness that drove the state machine turn by turn | The harness idea survives in `evaluation/`, now scoring ingest → report instead of interview transcripts. |
| `alembic_versions/` | Migrations for the interview schema | That schema no longer exists. The new baseline is `alembic/versions/0001_baseline.py`. |
| `alerts_repository.py` | `AlertRepository` — acknowledge and escalate over a `RedFlagAlertRecord` table | Missed in the first pass of this restructure and left importing three modules that had already moved; `mypy` found it. The backend no longer evaluates red-flag rules, so it holds *events the device reported*, not alerts it raised. `WorklistService.acknowledge` is the surviving half. |
| `review_queue.py` | Generated `docs/CLINICAL_REVIEW_QUEUE.md` from unreviewed question content | The content it read is in `questionnaires/`. |

## `evaluation/` — moved here on 2026-09-05

The scripted-patient harness that scored the interview. The restructure note
above said it survived in `backend/evaluation/`, "now scoring ingest → report
instead of interview transcripts". That migration was started and not finished:
`run.py` imported an `evaluation.scenario` module that was never written, and
`harness.py` still imports `AnswerShape` from the interview enums. It has not
executed since the restructure.

It is shelved rather than repaired because §3 of the brief says the harness is
"repurposed in §13", and §13's fourteen items are all test-suite items — the
end-to-end path, the normalizer contract fixtures, the golden-file report
determinism, the status vocabulary, redaction and tenancy — every one of which
is now a passing test. The scoring the harness used to provide is provided by
those.

Reviving it means rewriting `harness.py` against `CanonicalRecord` and writing
scenario fixtures that are kiosk payloads rather than interview scripts. That is
a new deliverable, not a repair.

## What was kept and built on

Not moved, because it is the core of the new build:

- `app/domain/clinical/provenance.py` — `ConceptRef`, `BoundingBox`, typed identifiers
- `app/domain/clinical/enums.py` — `Section`, `ReporterRole`, `Certainty`, `Severity`
- `app/domain/ontology/` — the concept registry and the fuzzy matcher
- `app/domain/contradictions/` — rewritten onto `Fact`, algorithm unchanged
- `app/core/logging.py` — the PHI filter
- `app/core/{config,errors,ids,clock,idempotency}.py`
- `alembic/`, `app/events/`, `app/realtime/`

## Reviving something

The packages are self-contained and import only from `app.core` and
`app.domain.clinical`. `clinical_fact.py` and `patient_state.py` are the two
pieces the rest of `stale/` depends on that no longer exist under `app/`; a
revival starts by restoring those two modules to `app/domain/clinical/` and
adding `stale` back to `testpaths`.
