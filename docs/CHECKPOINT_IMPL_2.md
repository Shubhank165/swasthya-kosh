# Checkpoint — Implementation 2 of 3 (Patient app, Flutter)

**2026-09-06, second session.** Both sides green:

```
backend   make lint / typecheck clean; make test -> 439 passed, 1 deselected
app       flutter analyze -> No issues found; flutter test -> 156 passed, 2 skipped
          make app-test-live -> 2 passed, against a running backend
          flutter build apk --debug -> built
```

Every item in §15 that can be closed from this machine is closed. The two pieces
the previous checkpoint deferred are built — **the flow controller** and
**submit-exactly-once** — and with them the app walks the whole of §5: language,
sign-in, hospital, consent, who it is for, the returning-patient check, the
interview, documents, review, submitted. An intake survives being interrupted,
being finished with no signal, and firing a red flag halfway through.

**One whole intake has now gone from the app's own code into a running backend**
and come back accepted: 75 fields, 69 answered, `status: complete`, neither
repaired nor flagged for manual review.

Nothing committed since `e4d93e1` (1/3, on `impl-1-backend-gcp`).
Brief: `MEDIKIOSK_IMPL_2of3_FLUTTER_APP.md`.

---

## Where things stand

| § | Area | State |
|---|---|---|
| 12 | Backend endpoints, `patient` role, ingest opened to it | **Done** |
| 3, 4 | Content bundle, both ends; bundle model + walker | **Done** |
| 9 | Record assembly, pinned against the shared fixture | **Done** |
| 8 | Document preparation: downscale, EXIF strip, quality | **Done** |
| 10 | Encrypted Drift database, drafts, clearing | **Done** |
| 14 | Nine ARB locales, theme, accessibility | **Done** |
| 4 | Eight answer-type renderers | **Done** |
| 5, 6 | Eleven screens | **Done** |
| **5, 6, 9** | **The flow controller** | **Done — 18 tests** |
| **9, 10** | **Submit exactly once** | **Done — 13 tests** |
| 11 | Consent: notice endpoint, screen wired, artefact filed | **Done — 4 backend tests** |
| **8** | **Document capture: pick, prepare, store, upload, delete** | **Done — 7 tests** |
| **5** | **Returning-patient check (screen 5)** | **Done — 3 tests** |
| **5** | **Ayurveda: full module first visit, current-state subset on return** | **Done — 4 tests** |
| **7.2** | **ABHA: optional, mocked, marked as mocked** | **Done — 5 tests** |
| **4** | **An unsupported bundle refuses the intake and says so** | **Done — 3 tests** |
| **10** | **Structured logging that cannot carry clinical text** | **Done** |
| 5 | Resume prompt, and the seven-day staleness rule | **Done** |
| 10 | Sign-out wipes the device, not just the token | **Done** |
| 15 | Items 1 (Android), 2, 3–14 | **Done** |
| 15 | Item 1 (iOS) | See "Not verified" |

---

## What was built this session

| File | What it is |
|---|---|
| `app/lib/intake/flow.dart` | **The flow controller.** Owns the walker, the draft, the screen sequence and the red-flag interaction. No clinical logic — it asks the walker and does as it is told |
| `app/lib/submit/queue.dart` | **The submission queue.** Enqueue, one-shot send, background flush, document upload, consent filing, purge |
| `app/lib/intake/intake_host.dart` | Turns a `FlowStage` into a screen. Deliberately thin |
| `app/lib/intake/begin.dart` | Consent gate and reporter gate — screens 3 and 4, in §11's order |
| `app/lib/consent/consent_repository.dart` | The notice, and the artefact it produces |
| `app/lib/documents/document_store.dart` | Pick, prepare, store. **The original bytes never reach disk** |
| `app/lib/identity/history_repository.dart` | What the hospital already holds, for screen 5 |
| `app/test/live_backend_test.dart` | The one test that talks to a real backend |
| `app/lib/core/logging.dart` | Event name and scalars. There is no `log(String)` |
| `app/lib/identity/abha_repository.dart`, `abha_screen.dart` | §7.2, offered and never asked for |
| `app/integration_test/journey_test.dart` | The whole §5 sequence. **Written, never executed** |
| `clinical/questions/ayurveda/ayurveda_module.yaml` | `current_state: true` on Agni, Nidra, Koshtha |
| `backend/app/api/v1/content.py` | `GET /content/consent`, with `source=app` filtering |
| `clinical/consent/consent_v1.yaml` | `applies_to: [kiosk]` on `raw_audio_retention` |

Supporting changes: `IntakeWalker.retract` / `lastAsked`; `Answer.fromDraftJson`
and a `value_kind` tag on the **draft** shape only; a `hospitalName` column on
`Drafts` (schema 2, with the migration); receipt and pending-document helpers;
`resumableDraftProvider`, `submissionQueueProvider`, `consentNoticeProvider`; a
launch-time flush in `main.dart`; the `hospital.continue` button that was the
dead end.

Decisions 46–51 in `DECISIONS.md` cover the reasoning. The three that are worth
reading before touching this code:

- **46** — exactly-once rests on three mechanisms, not one, and each covers a
  failure the others do not.
- **48** — the flow owns ordering and nothing else, and three of those orderings
  are load-bearing.
- **49** — going back discards the walker's derived conclusions and any answer
  no longer in the plan, or changing the chief complaint submits answers from a
  branch nobody walked.

---

## Defects found this session

| Defect | Found by |
|---|---|
| **Retracting one answer would have left the old branch's answers in the record** — changing the chief complaint from chest pain to fever kept `dyspnoea` | writing the back-navigation test |
| **A draft could not be resumed faithfully.** `toJson` is deliberately lossy — a coded option and free text both serialise to a bare string, which is what the backend's `coerce()` wants — so a round-trip had to guess. It now carries a tag on the draft shape, and only there | writing the resume test |
| **The kiosk's audio-retention purpose would have been shown in an app with no microphone**, filing a DPDP artefact describing something that never happened, on every intake | wiring the consent screen to real content |
| **A document that failed to upload would have been purged with the intake.** "Delete on submit" has to mean once the hospital has *everything* | writing the document test |
| **The app never sent `X-Hospital-Id`**, so a signed-in patient could do nothing at all — every request after sign-in was a 401. A patient session says *who*, not *where*, and the header is how the backend learns the second | the live end-to-end test, on its first run |
| **A fact carried forward from an earlier visit produced a turn** with `asked_text: null`, claiming the interview had shown the patient a prompt it never showed | the returning-patient test |
| **Sign-out cleared the token and left the database.** §10 says clear everything; a stranger's health answers behind a screen that merely looks signed out is the opposite | auditing §10 against the code |
| **Four screens existed and were wired to nothing** — documents, the returning-patient check, and with them the whole of §8's capture path: no `PendingDocuments` row was ever written, so the queue's upload code had no producer | auditing §5 screen by screen |
| **`api.dart` claimed to log method, path and status. Nothing logged at all** — the comment described an interceptor that was never written | auditing §13's `core/` list |
| **An unsupported bundle overwrote the cached one**, bricking an app that was holding a bundle it could still have used, and against a backend that still accepts the older contract | writing the version-gate test |
| **A blank ABHA address reached `PatientRef` and raised**, turning a client mistake into a 500 | the new endpoint's own test |
| **`sqlite3_flutter_libs` and `sqlcipher_flutter_libs` both register `Sqlite3FlutterLibsPlugin`**, which fails the dex merge — and had it linked, the app would have carried two SQLite builds and the first connection would have decided which one a patient's answers were written with | the APK build |

---

## The APK builds

```
✓ Built build/app/outputs/flutter-apk/app-debug.apk
```

Last session this was blocked on disk. With room to run, it got far enough to
surface a real defect — the duplicate SQLite plugin above — and builds cleanly
once that is fixed. §15 item 1 is done for Android.

Two things to know about this build:

- **The JDK override is still per-machine.** Flutter otherwise picks Android
  Studio's bundled Java 25 and fails with `Unsupported class file major version
  69`. `app/README.md` has the command.
- **Gradle warns that some plugins want NDK 27.0.12077973.** The build succeeds
  without it and nothing in this app has native code of its own, so it is left
  alone rather than pulling down an NDK on a machine at 98% disk. Set
  `ndkVersion` in `android/app/build.gradle` if a plugin ever needs it for real.

---

## Not verified

**§15 item 1 — iOS.** No Mac. The iOS project declares no microphone key in its
`Info.plist` and that is asserted in CI, which is all that can be said from
here.

**The app has not been driven by hand on a device.** `make app-test-live` proves
the code path end to end — real bundle, real sign-in, real ingest — but it
drives the flow controller directly rather than tapping the screens.
`integration_test/journey_test.dart` taps the whole §5 sequence and **has never
been executed**, because there is no device here and it cannot run on the host
(decision 59). That is the single largest remaining gap.

**Everything below `documents` in the queue is exercised against a fake
adapter**, apart from the ingest itself. The document upload has never run
against the real multipart endpoint.

**`go_router` is a dependency and is not used.** §13 names it in the stack;
navigation is `Navigator.push` at six call sites. The intake itself is
controller-driven by design — `IntakeHost` switches on `FlowStage` — so a router
would own the seven screens around it and hand the flow object through `extra`.
It is a mechanical refactor with runtime-only risk and nothing on this machine
that can verify navigation, which is why it was not done blind. Either adopt it
or drop the dependency; leaving it declared and unused is the one thing that is
not a defensible end state.

---

## Resume here

1. **Run `integration_test/journey_test.dart` on a device**, then tap through
   one intake by hand. Install the APK on an emulator, run the backend
   (`make dev-detached`), and use
   `--dart-define=MEDIKIOSK_BASE_URL=http://10.0.2.2:8000`. The code path is
   proven and the screens are covered individually; the sequence is not.
2. **Settle `go_router`** — adopt it for the seven screens around the intake, or
   drop the dependency and record why.
3. **GCP provisioning**, still requested. When doing it: `SQL_TIER` in
   `infra/gcp/config.sh` defaults to `db-custom-1-3840`, a dedicated-core custom
   tier larger than this workload needs. Make it a documented knob and drop the
   default to a shared-core tier.
4. **3/3 — the doctor dashboard.**

## How to run the live test

```
make dev-detached                      # or: postgres + alembic + uvicorn
make app-test-live LIVE_URL=http://localhost:8000
```

It reports as skipped without `MEDIKIOSK_LIVE`, so a normal `flutter test` on a
laptop with nothing running stays green rather than red-and-ignored.

---

## Open, carried forward

- **The Ayurveda current-state subset needs a clinician's confirmation.** The
  brief names digestion, appetite, sleep and bowel habit; that maps to
  `agni_appetite`, `nidra_sleep` and `koshtha_bowel`, and the mapping is now on
  the review queue.
- **The consent notice exists in English and Hindi only**, so seven of the nine
  UI languages stop at the consent screen rather than proceed. That is the safe
  failure (decision 51) and it is now the highest-value translation on the
  review queue.
- **Vertex residency** (`DECISIONS.md` §31) still not rewritten to say it blocks
  only the phone-upload path, not the kiosk.
- **`CLINICAL_REVIEW_QUEUE.md`** has the new `consentNotTranslated` string and
  the `applies_to` decision on item 8.
- **The evaluation harness** is still shelved.
