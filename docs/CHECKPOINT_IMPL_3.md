# Checkpoint — Implementation 3 of 3 (Doctor dashboard, and the carry-over)

**2026-09-06, third session.** All four suites green:

```
backend     make check    -> lint, typecheck, 483 passed (1 network test deselected)
dashboard   tsc --noEmit  -> clean
            eslint        -> clean
            vitest        -> 64 passed
            playwright    -> 7 passed, against a real backend
app         flutter analyze -> No issues found
            flutter test  -> 158 passed, 3 skipped (the live ones)
            flutter test test/live_backend_test.dart --dart-define=MEDIKIOSK_LIVE=…
                          -> 3 passed, against a running backend
            flutter test integration_test/journey_test.dart -d <phone>
                          -> 1 passed, on a physical Android device
stack       docker compose up -> postgres, migrate, seed, api:8000, dashboard:5173
```

Brief: `MEDIKIOSK_IMPL_3of3_DASHBOARD.md`.

---

## Part A — the dashboard

| § | Area | State |
|---|---|---|
| 3 | React 18 + TS + Vite, TanStack Query, Zustand, Router, Tailwind | **Done** |
| 3 | API client generated from the backend's OpenAPI | **Done** |
| 4.1 | Worklist: arrival order, pinned alert band, state filter | **Done** |
| 4.2 | Report: fixed section order, Unresolved and Conflicts as full sections | **Done** |
| 4.2 | Every fact state renders distinctly, by shape and label | **Done** |
| 4.3 | Alerts: unacknowledged first, acknowledge ≠ escalate | **Done** |
| 5 | Evidence panel: transcript, boxed document region, tapped option, prior visit | **Done** |
| 6 | Per-fact accept / amend / reject, inline editor, audit-logged | **Done** |
| 6 | Correction rate, admin-scoped | **Done** |
| 7 | WebSocket, refetch-on-reconnect, connection state shown | **Done** |
| 8 | Roles; `patient` and `kiosk` refused; idle timeout; no token in storage | **Done** |
| 9 | Semantic HTML, keyboard-workable report | **Done** |
| 9 | Doctor-facing UI in English **and Hindi** | **Done** |
| 10 | The four backend additions | **Done** |
| 11 | Tests 1–10 | **Done** |

**The interface translates; the record never does.** The chrome switches between
English and Hindi. A transcript, a raw OCR reading, a report line, a section
title and a red-flag label do not — they arrive from the backend in the language
the interview happened in, and a locale switch is not the place to reword a
clinical string an AIIA mentor signs off. Asserted in `test/i18n.test.tsx` and
again in the Playwright journey, because it is the kind of rule that quietly
stops being true when somebody adds a string next month.

The Hindi strings are engineer-authored and are on `CLINICAL_REVIEW_QUEUE.md`
like every other non-English string here. They are interface words —
"acknowledge", "amend", "worklist" — and one that is subtly wrong makes a control
mean something different to a Hindi-reading physician than to an English-reading
one.

**Sign-in is a stand-in and says so on screen.** There is no identity provider
integration, so the form sets the backend's header principal — which
`ALLOW_HEADER_AUTH` disables in any environment holding real data. The screen
carries a box saying exactly that.

---

## Part B — the carry-over

| § | Item | State |
|---|---|---|
| B1 | Drop `go_router` | **Done** (already absent; the only trace was a stale doc line) |
| B1 | Carried-forward provenance: schema 0.2 | **Done** — contract, normalizer, registry line, golden fixture |
| B2 | Run `integration_test/journey_test.dart` | **Done** — passes on a physical device |
| B2 | Document upload against the real multipart endpoint | **Done** — and it was broken |
| B2 | Vertex ML processing region | **Still open, and still yours** |
| B3 | Honest claims | **Done** — see `README.md` and below |
| B4 | Content needing a clinician | **Still open** — `CLINICAL_REVIEW_QUEUE.md` |
| B5 | Commit | **Done** |
| B5 | Local object storage | **Already done in 1/3**; the dashboard is now in the stack too |
| B5 | iOS | **Unverified, and said so** |

---

## What running the never-run tests found

§B2 predicted this: *"each live run found something no unit test could. Assume
this one will too."* Three, and the first is the serious one.

**1. Every intake from the app was being filed as `needs_manual_review`.**

The app sends `schema_version: 0.2`. The backend accepted 0.1. It had done so
for as long as the app had existed, and nothing failed anywhere:

- ingest answers an unparseable payload with a **200** by design — a device that
  keeps retrying eventually drops the intake, and the answers are worth more
  than the status code;
- the app checks the status code;
- so the patient saw a reference code and the doctor saw an intake with no
  canonical record behind it.

The cause was **two registries where §4.2 promised one**: the
version-to-normalizer map in `app/normalize/registry.py`, and a separate
version-to-contract map inside `app/services/repair.py`. Validation runs first,
so a version registered in one and not the other produces a backend that can map
a payload it will never accept. There is now one registry, in
`app/contracts/kiosk/__init__.py`, and a test asserting both key sets are
identical.

**2. Documents and consent artefacts were addressed to an intake that does not
exist.**

The kiosk contract specifies a UUID for `intake_id`. The app sends
`intake-<hex>`, so the backend derives a stable UUID rather than discarding a
finished interview — and the app kept using its own id for everything posted
*after* ingest. The document upload 404s, after the record was accepted, so the
patient is shown a successful submission and the doctor never sees the
prescription. The response's `intake_id` is now authoritative and is persisted
on the receipt, because the upload can be retried days later from a cold start.

**3. `integration_test/journey_test.dart` could not run on a device at all.**

`LocalDatabase.memory()` opened a connection without first pointing sqlite3 at
the SQLCipher build. On a host the system SQLite is present and the omission is
invisible — 158 host tests never saw it. On a device there is no `libsqlite3.so`,
because this app ships SQLCipher and deliberately not `sqlite3_flutter_libs`
beside it, and the first query threw before a screen rendered.

**And one from the dashboard's own journey:** a verified report came back as a
draft. The builder is pure and knows nothing about verification, verification
lives on the stored report row, and the report is regenerated on every read —
which is right, because a document that arrived since changes it. So the
sign-off was dropped on the way back out and every re-read of a signed record
showed it unverified.

---

## The claims that can now be made, and the ones that cannot

**Can:**

- Two intake paths — Jetson kiosk and Flutter app — produce the same record, and
  a physician reads it on a dashboard that traces every line to its source.
- The app's whole intake has gone into a running backend and come back accepted,
  including a photographed document through the real multipart endpoint.
- The eleven-screen app sequence passes on a physical Android device.
- `docker compose up` gives the complete system — kiosk-to-report *and* the
  screen to read it on — with no Google account and no network.

**Cannot, yet:**

- **"Nine languages"** is still not true. Questions exist in nine; the consent
  notice is English and Hindi only, and seven of the nine stop at the consent
  screen. That is the correct failure and the honest claim remains *"questions in
  nine languages, consent in two"* until a native speaker has translated the
  notice.
- **The old pitch metrics.** 100% required-field recall, 100% red-flag recall,
  zero unsupported assertions — those came from the evaluation harness now in
  `stale/`, which tested question selection, which lives on the Jetson. They do
  not describe this backend. The replacements are **repair rate** (live),
  **completion rate** (live) and **correction rate** (live as of this session) —
  and the correction rate returns `null` rather than `0.0` until a physician has
  actually reviewed something, because a zero on an empty denominator reads as
  "never wrong".
- **iOS.** Unverified, and it stays that way without a Mac. Android-only is a
  reasonable scope statement; implying iOS works is not.
- **The Vertex ML processing region.** Still unconfirmed, and the models are now
  on anyway in the `medikiosk-sih-2026` deployment — deliberately, on a project
  holding synthetic documents and no patient. `VERTEX_ZDR_ENABLED=true` is an
  operator's assertion, not evidence, and decision 31 now says so with a date.
  Real patient data still waits on the written answer.

---

## Still open, and none of it is code

Everything on `CLINICAL_REVIEW_QUEUE.md`. The Ayurveda return-visit subset, the
red-flag criteria and question order, the nine-language question translations,
and the app's urgent-care wording and emergency number. Every rule still carries
`clinical_source: pending`. A Vaidya and an AIIA mentor close these; an engineer
cannot.

---

## The models are on, and what that took

`/readyz` on the deployed API had been reporting `"ocr": "mock", "repair":
"mock"` since the day it went up, and nobody had read it. Not a blocker and not
a residency problem: `40-deploy.sh` never set either variable, so both took
their safe default. Decision 65 covers the shape of the fix — five knobs, mocks
still the default, and ZDR a separate switch that `config.sh` refuses to deploy
without.

**Both adapters have now run against a real project**, `asia-south1`, on a
Gemini Flash model — the first time either has, since they are excluded from
coverage and CI has no credentials for them. `backend/scripts/smoke_vertex.py`
is what runs them: a synthetic prescription in, six items with bounding boxes
and per-item confidence out, then a payload that fails the 0.2 contract in three
ways, repaired, with `"maybe two weeks, could be more"` still sitting there
unresolved.

It found two defects, in two calls.

| Defect | What it would have done |
|---|---|
| **`document_date: "04/09/2026"`** — the date as printed, against a `date` field. Pydantic raised out of the adapter, and nothing catches it | The row is already `processing`, so the Pub/Sub push 500s, burns all five delivery attempts and dead-letters a document a person could have read. Now: ISO-only, dropped if not, and any validation failure is a `REJECTED` verdict rather than an exception (decision 67) |
| **Repair invented `intake_id` and `hospital_id`** to satisfy required fields it had not been given | `ingest` sets `hospital_id` from the kiosk token *before* repair, so a changed one re-files the record under whatever the model wrote, past a tenancy guard that sees nothing wrong. `IDENTITY_KEYS` now throws the repair away rather than retrying (decision 66) |

The second is the one worth dwelling on. The repair instruction forbids
inventing, in capitals, twice. The model invented anyway — not maliciously and
not even unreasonably: the schema said the field was required and it had no
value to put there. That is the whole argument for re-validating a model's
output at the boundary rather than trusting the prompt, and it is now applied to
the four fields where invention does the most damage.

Provisioning also had one thing wrong, on the same reasoning that "only the
worker calls Vertex": true of OCR, false of repair, which runs on the API during
ingest. `40-deploy.sh` grants the API service account `roles/aiplatform.user`
when repair is Vertex, and only then.

Deployed shape:

```
project   medikiosk-sih-2026        region  asia-south1
image     medikiosk:50b8895         schema  at head
ocr       gemini                    repair  vertex
storage   gcs                       queue   pubsub (push -> worker)
```
