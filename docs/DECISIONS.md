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

---

# The patient app (2 of 3)

## 34. The question content is a contract between three parties

It moved out of `backend/stale/questionnaires/` and back into
`clinical/questions/`. The Jetson walks it to conduct a spoken interview, the
patient app walks it to render a touch form, and the backend compiles it into
the bundle both download.

**Why it moved back.** The note that sent it to `stale/` said "question content
belongs to the device that asks the questions". True while the Jetson was the
only asker. The app is a second one, and the alternatives were a second copy of
the content or a Dart reimplementation of the question logic — which is the
drift problem this project has spent three builds avoiding.

**The engine did not come back.** `app/domain/questions/` parses, validates and
compiles. Nothing in it evaluates a precondition or fires a rule.

## 35. Complaint concepts are resolved at compile time

Red-flag rules were authored against `{concept: chest_pain, status: present}`.
Nothing asks a question called `chest_pain`: the previous engine held facts
keyed by concept, so choosing a chief complaint made a concept of the same name
present. Read literally, **all seventeen complaint-gated rules could never
fire** — every cardiac, abdominal, fever, headache and joint criterion in the
system.

They are rewritten during compilation into `chief_complaint in [chest_pain]`.

**Why not teach the clients the implication.** That is clinical logic, and it
would need implementing three times — on the Jetson, in Dart, and in Python —
with no test that could prove the three agreed. Saying what the rule means once,
in the compiler, leaves a walker that can be entirely stupid.

**What that rewrite could have broken.** A rule ANDing two different complaint
tests can never fire, because a patient has one chief complaint. The meningitis
rule reads a headache and a fever; had its fever leaf been the complaint `fever`
rather than the screen question `associated_fever`, this change would have
silently disabled it. It reads `associated_fever`. `_check_no_rule_is_
unsatisfiable` now proves that for every rule rather than for the one somebody
thought to check.

## 36. Red-flag criteria keep their nesting

§4 of the brief illustrates a flat `all` list. The authored rules are not flat:
the cardiac criterion is `chest pain AND sudden onset AND (breathless OR cold
sweat)`. Flattening it would require both symptoms — a strictly narrower rule,
on the criterion that exists to catch a myocardial infarction in a waiting room.

## 37. A missing prompt is never filled in with English

The backend refuses to start if a question lacks a prompt in a language the
bundle advertises. The app records `not_asked` for any question with no prompt
in the patient's language, rather than showing the English one.

**Why.** A patient answering a question in a language they did not choose
produces a record stating they answered something they may not have understood.
That is a false record, not a cosmetic problem — and it is invisible afterwards,
because the answer looks exactly like a real one.

**Consequence.** The bundle offers `en` and `hi`; the app's own chrome offers
nine. Those are different artefacts with different review requirements, and the
gap is listed in `CLINICAL_REVIEW_QUEUE.md` rather than closed by machine
translation.

## 38. Patient phone numbers are peppered HMACs, never digests

An Indian mobile number is ten digits — under a billion candidates. A plain
SHA-256 is reversed by exhaustive search in seconds, so a bare digest of a phone
number is the phone book with extra steps. `phone_ref()` refuses to run without
`PATIENT_REF_PEPPER` rather than falling back, because a fallback is the failure
mode where everything works and the privacy property is silently absent.

## 39. The OTP attempt counter is committed before the comparison

Not merely incremented. The request-scoped session rolls back on any exception,
and a wrong guess raises `UnauthorizedError` — so an uncommitted increment is
undone by the very error it was counting. The counter read zero forever and the
attempt cap was decoration: a six-digit code with unlimited guesses is a few
hours of scripted requests.

Found by the rate-limit test, not by review.

## 40. The patient-auth tables are tenancy-exempt, and opaque

`otp_challenges` and `patient_sessions` sit outside the tenant guard, because a
person signs into the app before choosing a hospital and their phone is not any
hospital's property. That widens a set 1/3 asserted as "reference data only".

**What makes it defensible rather than merely necessary**: neither table holds a
plaintext phone number, a code, or a usable token. `test_tenancy.py` now asserts
that by column name, so a debugging convenience cannot quietly reintroduce one.

## 41. `Role.PATIENT` inherits nothing and is inherited by nothing

Not symmetric with `KIOSK`. Staff must not acquire a patient's rights by
implication, because "read this patient's own history" is scoped by *whose*
history it is — which a role hierarchy cannot express. Staff read patient data
through routes that name a patient explicitly and are audited.
`GET /patients/me/history` takes no path parameter at all: the patient comes
from the session token, so there is nothing to tamper with.

## 42. An app answer carries no confidence score

The Jetson reports ASR confidence. A tap has none, and `1.0` would make a tapped
answer look like a perfectly-heard spoken one to every downstream consumer.
Absent is the honest value.

## 43. A red-flag abort submits the partial record

The intake stops and the patient is sent to urgent care, and everything answered
up to that point goes to the hospital with `status: aborted_red_flag`.

A patient being sent to an emergency department is exactly when the hospital most
wants the answers that sent them there. Discarding them because the intake did
not finish would throw away the most clinically loaded record the system
produces.

## 44. Metadata is stripped explicitly, not by re-encoding

`copyResize` copies the source image's `ExifData` onto the new image and the JPEG
encoder writes it back out — so "we re-encode, therefore EXIF is gone" is false,
and the pipeline was leaking camera make and model until a test proved it.
`prepare()` now replaces the whole `ExifData`.

The whole block rather than named tags: a prescription photographed at home
carries the patient's home coordinates, and stripping tag by tag leaves whatever
the encoder did not understand.

## 45. `minSdk` is 24, for the consent read-aloud

`flutter_tts` requires it. That dependency exists for one screen — reading the
consent notice aloud (§11) — which is the one place audio is warranted in a
touch-only app, and it is output, never input. API 24 is Android 7.0 (2016). The
alternative was dropping read-aloud, an accessibility regression for exactly the
patients who need it most.

---

# Open questions

## 46. Exactly-once submission rests on three things, not one

`app/lib/submit/queue.dart`

"Poor signal must not lose an intake" (2/3 §9) has a second half nobody writes
down: poor signal must not submit one twice either. A patient who taps send in a
lift and walks out must end up with exactly one record — not zero, and not two
for a registration clerk to reconcile with a queue forming behind them.

Three mechanisms hold that, and each covers a failure the others do not:

| Mechanism | Covers |
|---|---|
| One `Idempotency-Key` per **intake**, generated when the intake starts | A retry the server sees. A key per attempt would make every retry a new intake, which is the bug the header exists to prevent |
| A **receipt row**, written the instant the hospital accepts | A retry the server never hears about — a crash between acceptance and cleanup. Without it, the next launch posts again |
| **Nothing is deleted until it has been accepted** | Everything else. The draft, the assembled payload and the document files survive every failure; purge is the last step |

The ordering is the whole of the correctness argument and is written out once,
in `_run`, in numbered steps. A 4xx keeps the intake rather than dropping it:
the backend answers an unparseable payload with a 200 and `needs_manual_review`,
so a 4xx here is an expired token or a route that moved, and neither is a
problem a device should resolve by deleting a patient's answers.

## 47. The reference code is derived on the device, not issued by the backend

`referenceCodeFor()` in the same file.

It has to exist on a phone that has not reached the backend yet — an intake
finished on a train still gets a code, and the code still has to find the record
when the queue drains days later. Deriving it from the intake id means there is
no second identifier to keep in step and no column to add. It is **not a
secret**: it identifies a record to staff who can already see it, and anything
stronger would be a password the patient has to remember while ill.

## 48. The flow controller sequences; the walker decides

`app/lib/intake/flow.dart`

§1 rule 2 says the app is a renderer, not a brain, and §16 forbids a second
place that makes clinical decisions. The flow controller therefore owns the
*order of events* and nothing else: it never decides what to ask, what is
applicable, or what constitutes a red flag — it asks the walker and does as it
is told.

What it does own is ordering, and three orderings are load-bearing:

- **On an answer:** record, persist, *then* show the next question. §15 item 7
  kills the app at an arbitrary moment, and the arbitrary moment it will pick is
  between two questions.
- **On a red flag:** stop and show the urgent screen *before* any I/O, then
  persist, then queue the partial record. §6 gives that order, and "show it once
  the database write finishes" is a rule that decays into "show it once the
  upload finishes" the first time somebody moves a line.
- **On submit:** queue before send, always. An intake that exists only in memory
  when the radio fails is an intake lost.

## 49. Going back retracts derived conclusions, not just the answer

`IntakeWalker.retract`

Back and the review screen's edit both go through one method, and it discards
three things: the answer itself, every status the walker *derived* while
scanning ahead, and every answer no longer in the plan.

The second and third are necessary rather than tidy. A `not_applicable` was a
conclusion drawn from the retracted answer and has to be reached again. And
changing the chief complaint changes the branch — leaving the old branch's
answers in the map would submit answers to questions this intake no longer asks,
against a pathway nobody walked.

The discriminator between "the patient's answer" and "the walker's conclusion"
is `asked_text`, which is set exactly when a prompt was rendered on a screen. It
is the same field §9 requires for a different reason, and the two uses agree:
what was shown to the patient is what the patient answered.

**Retract refuses once a red flag has fired.** §6.4 says there is no "continue
anyway", and back is a continue.

## 50. Consent travels with the record and is filed after it

`app/lib/consent/consent_repository.dart`, `GET /content/consent`

The consent artefact references an intake, and the backend has not seen the
intake while the patient is tapping through the consent screen. So the grant is
carried on the queued envelope beside the record and filed the moment the intake
exists — before the documents, because a document processed under a consent that
was never filed is the ordering §11 cannot tolerate, and before the purge,
because an intake at the hospital with no record of what the patient agreed to
is the position §11 exists to prevent.

A retry after a crash between the post and the purge can file the artefact
twice. That is the acceptable direction of the two: artefacts are immutable and
append-only, so a duplicate is a second identical record of the same grant.
Treating a failure as filed would leave an intake with no consent record at all.

`source=app` on the notice endpoint omits `raw_audio_retention`, because this
app has no microphone and asking for consent to retain audio it cannot capture
would file an artefact describing something that never happened — for every app
intake.

## 51. A consent notice with no translation stops the intake

`ConsentGate` in `app/lib/intake/begin.dart`

The UI speaks nine languages; the consent notice is authored in two. Where a
question with no prompt in the patient's language records `not_asked` and moves
on (decision 37), consent cannot: agreement to text in a language the patient
did not choose is not agreement, and there is no "record it as unasked and carry
on" for a legal basis.

So the intake stops, and the message that stops it names the two languages that
do have a notice **in their own scripts**, so the way out is legible to somebody
who cannot read the sentence around it. The consequence is real and is on the
review queue: seven of the nine languages cannot complete an app intake until
the notice is translated.

## 52. A patient session says who, not where

`X-Hospital-Id` in `app/lib/core/api.dart`; `backend/app/api/auth.py`.

A kiosk's token is bound to exactly one hospital, and that binding — not the
request body — decides which hospital an intake belongs to. A patient's token
cannot work that way: the same person may complete an intake for whichever
hospital they are travelling to, and the credential says *who they are*, not
*where they are going*. So the backend takes the hospital from a header and
refuses a patient request that omits it.

The app was omitting it. Every unit test passed, sign-in worked, and the first
request that mattered came back `401 X-Hospital-Id is required`. Nothing but a
real backend was ever going to catch that, which is the argument for decision 53.

## 53. One test talks to a real backend, and only one

`app/test/live_backend_test.dart`, `make app-test-live`

Every other test in the app stubs the network at the dio adapter, which is the
right default: they are fast, they are deterministic, and they assert things
about headers and orderings that a live server would make harder to see, not
easier.

But a stub answers what it was told to answer. It cannot tell you that the
record you assembled is one the backend's normalizer accepts, and it cannot tell
you that a header you never sent was required — both of which were true of this
app until this test ran. So exactly one test fetches the real bundle, signs in
through the real OTP endpoints, walks whatever questions the content actually
contains, and posts the result to a running `/intakes/ingest`.

It reports as **skipped** without `--dart-define=MEDIKIOSK_LIVE=...`, so a
normal `flutter test` on a laptop with nothing running stays green and honest
rather than red and ignored.

## 54. A carried fact produces no turn

`IntakeRecordBuilder.build`, and `Answer.wasPut`

A fact carried forward from an earlier visit and confirmed on screen 5 is
`answered`, and it was never asked in this interview. Building a turn for it
would put an entry into `turns` with `asked_text: null` and claim the patient
was shown a prompt they never saw — in a record whose whole value is that a
physician can trace any fact back to the moment it was said.

So a turn requires the question to have actually been put, which is what
`asked_text` records and what `wasPut` reads. The consequence is a field that is
`answered` with `source_turn: null`, which reads exactly as it should: the
hospital holds this, and nothing in this interview asked it.

**The contract has no place to say where it came from.** `source_turn: null` is
an absence, not a provenance, and a reader has to infer "carried forward" from
it. A `carried_from_intake` field on the field entry would say it outright; that
is a v0.2 change, and it is on the review queue rather than invented here.

## 55. The return-visit Ayurveda subset is content, not a list in the app

`clinical/questions/ayurveda/ayurveda_module.yaml` (`current_state: true`),
`ayurveda_current_state` in the compiled bundle.

§5 screen 8 asks for the full Ayurveda module on a first visit and a
current-state subset on a return — digestion and appetite, sleep, bowel habit.
Which items those are is a clinical judgement, and a clinical judgement written
as a Dart list would be the second place clinical decisions live, which §16
forbids for good reason.

So the content marks them, the compiler emits a second list, and the walker
chooses between two lists the bundle handed it. **A bundle that names no subset
falls back to the full module**: a returning patient answering nine questions
instead of three is slower, and one asked none of them arrives without today's
Agni, Nidra or Koshtha at all.

A resumed intake keeps the plan it started with, which is why `return_visit` is
a column on the draft rather than re-derived. Re-deciding it mid-intake would
change which questions remain, and a patient who answered six of them before the
app died must not come back to a list that drops three from the record.

## 56. ABHA is offered, never asked for

`app/lib/identity/abha_screen.dart`, `POST /patients/me/abha`

§7.2: never mandatory, mocked for now, and the mock says so. Three things
encode that rather than merely intending it:

- **Continue is the filled button and linking is the outlined one.** The
  emphasis says which of the two the patient actually needs.
- **A failed lookup, an unreachable gateway, and tapping past the screen all
  reach the same next screen.** There is no failure path out of it, because
  there is no failure here that matters.
- **The mock notice is on screen, not in a log.** A demo that presents a mocked
  government integration as a live one is a claim nobody in the room can check.

The route is patient-scoped (`/me/abha`) rather than the existing
`/patients/resolve`, which is kiosk-or-staff: a patient linking their own
address must not be reaching a route that can resolve anybody's.

## 57. Logging takes an event name and scalars, and cannot take a sentence

`app/lib/core/logging.dart`

"No clinical data in logs, crash reports or analytics" (§10) is a rule that gets
broken in a hurry, so the convenient thing is the compliant one: there is no
`log(String message)` to reach for. `logEvent` takes a name and a map of small
values, and it emits nothing at all in a release build — a stream of intake ids
in logcat on a patient's phone benefits no one.

This also makes §4's "log a content-version mismatch" real. The walker still
does no IO — it holds no logger, which is what lets every safety test run
against it directly — so it collects the ids it could not render and the flow
logs them.

## 58. An unsupported bundle must not evict a working one

`BundleRepository.load`

§4 says a bundle naming a schema this app cannot produce means refusing to start
an intake and telling the patient to update. The subtlety is what happens to the
copy already on the phone.

Caching the new one would brick an app that was holding a perfectly usable
bundle — and needlessly, because the backend's normalizers accept every schema
version they support, so records against the older contract are still welcome.
So an unusable bundle is never written to the cache and never displaces one; it
is only handed back when there is no cache at all, which is the case where there
is genuinely nothing to run and `updateRequired` belongs on screen.

## 59. The journey test lives in `integration_test/` because it cannot run on
the host

`app/integration_test/journey_test.dart`

It was written under `test/` first and hung rather than failed. `testWidgets`
drives a fake clock; the encrypted database completes its queries on real async
work the fake clock never advances. Every existing test avoids the collision by
touching one or the other — drift without widgets, or widgets without drift —
and a whole-journey test needs both.

Moving it is the honest fix rather than sprinkling `runAsync` through a
twenty-tap sequence. It has **not been executed**: there is no device here. What
it adds over the tests that do run is the seam between the flow controller and
the screens, and that seam is precisely what is still unverified.

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
