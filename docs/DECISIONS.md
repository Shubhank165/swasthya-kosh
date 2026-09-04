# Architectural decisions

Every choice this build made that a reader could reasonably have made
differently, and why it went the way it did. Where a decision closed off an
option, the option is named — a decision log that lists only what was chosen is
a press release.

This log covers **Implementation 1 of 3: backend and GCP**
(`MEDIKIOSK_IMPL_1of3_BACKEND_GCP.md`). It replaces the log written for the
previous, interview-running build; that system's `ClinicalFact`,
`PatientIntakeState` and queue-preference machinery are in `backend/stale/` and
their decisions are no longer live. The last section is the honest list of what
is still open, including **one item that blocks turning on cloud models at all**.

---

# The record

## 1. Five statuses, and nothing may collapse two of them

`FieldStatus` is `ANSWERED | UNRESOLVED | NOT_ASKED | NOT_APPLICABLE | REFUSED`.

**Why.** "Nobody asked about allergies", "the kiosk asked twice and could not
bind an answer", "the patient declined to say" and "the question cannot apply to
this patient" are four different medico-legal positions, and none of them is
"no". A boolean holds one. An `Optional[bool]` holds three of the five, which is
worse than one because it looks sufficient.

**How it is held.** The vocabulary arrives from the kiosk and must survive
normalisation, storage, report rendering and FHIR export unchanged.
`tests/safety/test_status_vocabulary.py` proves the five stay distinct the whole
way; `tests/adapters/test_fhir.py` asserts
`set(FieldStatus) - {ANSWERED} == set(ABSENT_REASONS)`, so adding a sixth status
without deciding how it exports fails the build rather than defaulting to
"unknown".

**Cost.** Every consumer must handle five cases. That is the point.

## 2. Certainty may never increase, except by a human act

`Certainty` is `CONFIRMED | REPORTED | APPROXIMATE | UNCERTAIN`. A revision that
claims more confidence than the fact it supersedes raises
`CertaintyIncreaseError`.

**Why.** `"maybe about two weeks"` becoming `"2 weeks"` somewhere between the
kiosk and the report is the single most plausible way this system tells a
physician something the patient never said. Normalisation, repair and rendering
all have a natural pull in that direction, because a tidy value is easier to
handle than a hedged one.

**The one exception.** Physician verification, which writes a new revision
recording who verified it and when. A human raising certainty is a clinical act
with a name attached; code raising it is a bug.

**Consequence.** `ReportService.verify` skips unsettled fields rather than
marking them verified. There is nothing to confirm about a question that was
never asked, and confirming one would turn an unresolved field into an
established one with a physician's name on it — the exact move the invariant
exists to prevent.

## 3. `original_text` travels with every fact, forever

**Why.** The normalised value is an interpretation. When a physician asks "what
did they actually say?", the answer has to exist, in the patient's own words and
in the language they used. This is also the only defence against a normaliser
that is subtly wrong: the evidence outlives the interpretation.

**Consequence.** `GET /intakes/{id}/facts/{fact_id}` returns the transcript turn
or the document region behind one line of the report, which is why every fact
carries a `SourceRef`.

## 4. Facts are append-only; a correction is a new revision

`Fact` is frozen. Corrections produce a new fact whose `supersedes` points at
the old one, and there is no UPDATE path to the fact table anywhere in the
codebase.

**Why.** "The physician confirmed this at 10:42" is itself a fact with a
timestamp. An audit trail that can be edited is a document, not a trail.

---

# Ingest

## 5. A malformed payload is stored, not rejected

Payloads that fail contract validation go to `ingest_raw` and the intake is
marked for manual review.

**Why.** The kiosk is a device in a corridor, running a build that may be older
than the server's. Rejecting its payload loses a patient's interview; storing it
loses nothing and makes the failure visible to a person.

## 6. Repair is the only place a model touches clinical input, and it is optional

`REPAIR_PROVIDER=none` is a supported production configuration.

**Why.** A hospital that will not have a model touch patient input at all still
gets ingest, documents, contradictions and the report. The outcome without
repair is worse — more payloads land in `ingest_raw` — but it is honest, and the
choice belongs to the hospital rather than to this repository's defaults.

## 7. Idempotency is per endpoint, not middleware

Each mutating route wraps its work in the idempotency guard; the OpenAPI
completeness test fails the build if a POST/PATCH/PUT appears without the header.

**Why not middleware.** Middleware was the first design and would have covered
every future route automatically. It has to buffer the request body to
fingerprint it — which means buffering a multipart photograph of a prescription
into memory, on the one endpoint where the payload is large. The per-endpoint
helper is a few lines per route and leaves the upload alone.

**And a retry with no key at all is still safe.** A kiosk that lost the LAN
mid-request and resent without a key gets its original intake back rather than a
duplicate, because ingest short-circuits on the intake id. This was a 500 until
this build; see the defect list in `docs/CHECKPOINT_IMPL_1.md`.

---

# Documents

## 8. A document never overwrites what the patient said

An extracted medication becomes its own fact from a `DocumentSource`, beside the
spoken one. Where the two disagree, the disagreement is reported.

**Why.** A printed prescription is evidence of what was prescribed, not evidence
of what the patient is taking. "The scan says 900 mg and the patient says 500
mg" is clinically interesting; silently preferring either is clinically
dangerous.

## 9. Medication aliases are derived on read, never stored

`align_medications` derives alias facts so a spoken "Metformin" and a printed
"Tab. Metformin 900.2 mg BD" compare on the same field id.

**Why derived.** A change to the ingredient table then applies to records already
stored. Persisting the aliases would freeze each record against the table as it
stood on the day of the visit.

**Why it matters clinically.** Without alignment the prescription shows up as a
medicine the patient failed to mention — which they did not — and the real
finding, a dose discrepancy, is not reported at all.

## 10. A lab value is compared only against the range printed on the same document

When the document carries no range, the result is `RANGE_UNAVAILABLE` and is
never flagged.

**Why.** Reference ranges vary by assay, by analyser and by laboratory. A
built-in range table would flag a normal result as abnormal whenever the lab
used a different method, and "your report says this is high" from a kiosk is a
thing a patient will believe.

## 11. Drug interactions come from sourced rows, and there is no herb–drug prediction

`clinical/interactions/` is a table with a citation per row. Nothing infers an
interaction that is not in it.

**Why.** An AYUSH OPD is exactly where herb–drug interaction prediction would be
most tempting and least defensible: the evidence base is thin, and a plausible
false positive would have a physician stop a patient's Ayurvedic medicine on the
authority of a kiosk. Absent evidence, the honest output is silence.

## 12. Document processing is idempotent

`DocumentService.process` returns the existing extraction when the document is
already `PROCESSED` or `REJECTED_QUALITY`.

**Why.** Pub/Sub is at-least-once. A redelivery — which happens for ordinary
reasons like an ack that arrived after the deadline — duplicated every extracted
line, so a five-medicine prescription became ten. This was found by writing the
redelivery test, not in review.

## 13. The queue message carries identifiers and nothing clinical

The Pub/Sub message is `{hospital_id, intake_id, document_id}`, duplicated as
attributes. The worker re-reads everything else.

**Why.** A Pub/Sub message is retained for days, is readable by anyone with
subscriber rights on the topic, and is copied into a dead-letter topic when it
fails. None of those is a place a prescription belongs.

## 14. On the push endpoint, the HTTP status code *is* the retry policy

`204` for done or permanently undoable; `5xx` for transient.

**Why it is chosen rather than defaulted.** Getting it backwards is expensive in
both directions. A permanent failure marked retryable pins a worker to one bad
message for the whole retention window; a transient failure acknowledged drops a
patient's prescription silently, and nobody finds out. So a malformed envelope
and an unknown document id both return 204 and log at warning, and a provider
outage returns 500.

## 15. A failure to queue fails the upload; a failure to process does not

The dispatch is awaited and its exception reaches the caller. OCR failure, once
queued, is swallowed and leaves the document unread.

**Why the asymmetry.** After queuing, the response has gone out and the image is
stored: the honest state is a document the report shows as "not yet processed",
and raising would only make the kiosk resend a photograph that arrived. Before
queuing, nothing exists to retry — a document accepted and never queued is one
the physician is never shown and never told about, so the kiosk is better off
seeing the upload fail.

---

# Report and export

## 16. Contradictions are recomputed on every read, never stored

**Why.** A document that arrives an hour after ingest changes what conflicts.
Recomputing means the physician sees today's answer against today's evidence
without anything being re-ingested.

## 17. The report is template-assembled per language, never translated at runtime

`clinical/report_templates/{en,hi}/`. A language is offered only if templates
exist for it.

**Why.** Machine-translating a clinical summary at request time puts a model
between the record and the physician, in the last place anyone would check it. A
language with no reviewed template is a language this system does not speak.

**Default.** The report renders in the patient's own language unless one is
requested, which surprised a test author during this build and is the correct
behaviour.

## 18. The FHIR bundle is byte-stable, and never invents a code

Unsettled facts export with `dataAbsentReason`; a fact with no terminology
mapping exports with text and no coding.

**Why byte-stable.** A bundle that differs between two identical requests cannot
be diffed, cached or checked against a golden file, and every downstream
integration then has to normalise before comparing.

**Why never invent.** A guessed ICD-11 code is indistinguishable, downstream,
from a clinician-assigned one.

## 19. FHIR resource ids are sanitised, and `fullUrl` is a real base URL

R4's `id` datatype is `[A-Za-z0-9\-\.]{1,64}`; every field id in this system
contains an underscore. `resource_id()` substitutes illegal characters and
hash-suffixes anything over 64 characters. `fullUrl` is
`https://medikiosk.in/fhir/{Type}/{id}`.

**Why.** The published HAPI validator rejected the entire bundle: *Invalid
Resource id: Invalid Characters*, and *UUIDs must be valid and lowercase* for
`urn:uuid:` prefixes on ids that are not UUIDs. The bundle now validates with
zero errors, checked by `tests/adapters/test_fhir.py` under `-m network` and by
an offline structural check that asserts the same two rules on every run.

**Three warnings remain, deliberately.** No `Observation.performer` (the
observer is a kiosk, and naming a practitioner who was not there would be
false), no generated narrative (`dom-6` is a best-practice rule), and unknown
CodeSystems for ICD-11 and NAMASTE (the validator does not have them; that is
not a defect in the bundle).

---

# Data

## 20. An unscoped query raises, and is not auto-scoped

`app/db/tenancy.py` listens on `do_orm_execute` and raises `MissingTenantFilter`
naming the tables involved.

**Why not silently add the filter.** Auto-scoping makes the mistake invisible and
trains everybody to stop writing the predicate. The failure mode it protects
against — one hospital seeing another's OPD — is a reportable breach that looks
exactly like a working feature until somebody notices.

**It now covers writes.** `Update` and `Delete` carry a single target table and
have no `get_final_froms`, so the guard raised `AttributeError` on them instead
of `MissingTenantFilter`. The statement was still refused, but for a reason
nobody would read as a tenancy problem — and one defensive `except Exception`
anywhere above it would have turned that refusal into a silent cross-hospital
write.

## 21. The token's hospital beats the request body

**Why.** A misconfigured kiosk claiming another hospital must be ignored, not
obeyed. The credential is scoped to one facility and that scope is the
authority.

## 22. Report dates are the hospital's calendar day

**Why.** "Today's OPD" means today where the hospital is. IST differs from UTC
by five and a half hours every night, which is precisely when an evening clinic
would file its reports under yesterday.

---

# Deployment

## 23. Migrations are a pre-deploy step and `serve` does not run them

**Why.** With `min-instances 0`, the morning's first patients cold-start several
API containers at once, each running `alembic upgrade head` against the same
database. Worse, it means rolling the application back is not a rollback,
because the schema has already moved. One runner, before traffic:
`make migrate-cloud`, or the one-shot `migrate` service in compose.

**Cost.** A forgotten migration step now produces a clear failure at startup
instead of a schema that silently caught up. That is the trade.

## 24. One image, three roles

The API, the OCR worker and the migration job are the same bytes, differing only
by environment and by the argument passed to the entrypoint.

**Why.** An image smoke-tested as the API is the image that later runs the
migration, so "it worked in staging" means something.

## 25. The worker route does not exist on the public API

`PUBSUB_PUSH_ENABLED` registers the router. The public service leaves it unset.

**Why.** An endpoint that is absent cannot be probed. The alternative — publish
it everywhere and guard it — leaves the guard as the only thing between the
internet and a route that processes documents for an arbitrary hospital id.

**How it is held.** `infra/gcp/40-deploy.sh` asserts on every deploy that the
public API answers 404 for `POST /api/v1/worker/documents`, and fails the deploy
if it answers anything else.

## 26. Three service accounts, not one

API, worker and push identity are separate, and secrets are granted one at a
time rather than project-wide.

**Why.** A single shared account makes the blast radius of any one leaked
credential the whole system, and `roles/secretmanager.secretAccessor` at project
scope silently grants access to the next secret somebody adds.

## 27. There is no MinIO in the compose file, and the brief asked for one

**The deviation, stated plainly.** §11 lists Postgres, MinIO, the API and the
worker. This build ships Postgres, a one-shot migrate, a one-shot seed, the API,
and the worker behind a profile — with document storage on a named volume.

**Why.** `app/adapters/storage/stores.py` implements `local` and `gcs`. There is
no S3-compatible store, so a MinIO container would be a service nothing talks
to: it would appear in `docker compose ps`, look like working infrastructure,
and be wired to nothing. The deliverable §11 actually asks for is "full stack on
a laptop, no GCP", and local disk on a named volume is the storage backend the
code supports.

**What it would take to close.** An `S3ObjectStore` implementing the four-method
`ObjectStore` protocol, `boto3` or `aiobotocore` in the `dev` extra, a
`storage_backend` validator entry, and the store's own tests. Perhaps an
afternoon. It was not done because nothing in the demo path or the GCP target
needs it, and an untested storage backend is a liability rather than a feature.

**Who decides.** If on-prem S3-compatible storage is a requirement for a hospital
deployment, this is the thing to build next in §11.

## 28. The worker is in compose behind a profile, not in the default stack

`docker compose --profile worker up`.

**Why not in the default.** With no broker, the API processes uploads in a
background task — that is what makes the laptop path a complete pipeline
offline. A worker in the default stack would sit idle and be mistaken for the
thing doing the work.

**Why present at all.** It proves the image boots in the worker role and lets
`POST /api/v1/worker/documents` be exercised by hand against a real database
before anything is deployed.

## 29. `EVENT_BUS` was deleted rather than left as a switch

There was a `PubSubBus` whose every method raised `NotImplementedError`, and an
`EVENT_BUS` setting that selected it. Both are gone.

**Why.** A setting that silently does nothing is worse than no setting: somebody
sets `EVENT_BUS=pubsub`, sees no error at startup, and believes a second API
instance is receiving events. Dashboard fan-out is in-process, and this is now
the documented truth rather than a config option that looks like a capability.

**What genuinely spans instances** is the OCR work queue, which is a different
problem with a real implementation — `app/adapters/queue/dispatch.py`, with both
paths ending at the same `DocumentService.process` so they cannot drift.

## 30. Everything is `asia-south1`, enforced in the script

`infra/gcp/config.sh` refuses any region outside `asia-south1`/`asia-south2`.

**Why a check rather than a default.** A default is a thing somebody overrides
during a demo at 2am. Patient data for an Indian hospital staying in India is
not a preference.

---

# Open questions

## 31. BLOCKER — Vertex ML processing residency is unverified

**Status: open. Nothing turns on `OCR_PROVIDER=gemini` or
`REPAIR_PROVIDER=vertex` in an environment holding real patient data until this
is answered and written down here.**

`app/adapters/ocr/gemini.py` and `app/adapters/llm/vertex.py` both refuse to
construct unless `VERTEX_REGION` is `asia-south1` or `asia-south2` **and**
`VERTEX_ZDR_ENABLED` is true. Those guards are real and are tested.

What they do **not** establish is that *ML processing* — as distinct from
storage at rest — stays in region for the specific model in use. Google
documents data residency commitments per product and per model, and the set of
models covered for at-rest storage is not the same as the set covered for
processing.

**What has to happen.** Somebody with access to the project's terms confirms, in
writing, for the exact model id configured: (a) that inference is performed in
region, (b) that Zero Data Retention applies to it, and (c) that neither changes
when the model is versioned up. The finding — either way — belongs in this file
with a date and a source.

**This is a decision for the team, not for the agent that wrote this code.** The
guards deliberately fail closed so that shipping without the answer is
impossible rather than merely inadvisable.

## 32. Clinical content pending review

Engineer-authored, each file saying so in its own header, and none of it
reviewed by a clinician:

- `clinical/report_templates/hi/` — the Hindi report templates and field labels.
  Written by an engineer with reference material, which is not the same as
  written by a Vaidya. The English templates are the ones that have had eyes on
  them.
- `clinical/interactions/` — the seed interaction table. Every row is sourced,
  but the selection of which interactions to include is not a reviewed clinical
  judgement.
- The terminology seeds, listed in `docs/CLINICAL_REVIEW_QUEUE.md`.

**Why it ships anyway.** The alternative is an English-only report in a Hindi-
speaking OPD. The templates are marked, the review queue names them, and nothing
in them states a diagnosis or gives advice.

## 33. Known gaps

- **Authentication for staff is a header stand-in.** `X-User-Id` /
  `X-User-Role` fail closed on an unknown role and the role checks are real, but
  real authentication is the hospital's identity provider.
  `ALLOW_HEADER_AUTH=false` is set on every cloud deployment, which means the
  dashboard needs that integration before it has a live user.
- **Kiosk tokens are static shared secrets** in Secret Manager. Adequate for
  devices in a controlled corridor; rotation is manual and there is no
  per-device revocation beyond editing the map.
- **The FHIR bundle is served but not pushed.** `GET /intakes/{id}/fhir` returns
  a validated R4 bundle; delivering it into a hospital HMIS needs a real
  endpoint to integrate against.
- **No S3-compatible object store**, per decision 27.
- **The evaluation harness is shelved, not repurposed.** §3 of the brief kept it
  for reuse in §13; the migration was started and left half-done —
  `evaluation/run.py` imported a module that was never written, and it had not
  executed since the restructure. §13's fourteen items are all test-suite items
  and all pass, so the scoring it used to provide exists; the scripted-patient
  metrics table does not. `backend/stale/README.md` says what reviving it means.
- **Dashboard fan-out is single-instance**, per decision 29. The API runs with
  `max-instances 10`; a WebSocket client connected to one instance does not see
  events published on another. This is invisible in the demo and would need a
  broker-backed bus before a multi-instance dashboard is real.
