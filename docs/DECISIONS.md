# Architectural decisions

Every choice made in this build, and why. Where a decision closed off an option,
the option is named — a decision record that only lists what was chosen is a
press release.

---

## 1. The domain layer is pure, and enforced to be

`app/domain/**` imports no FastAPI, no SQLAlchemy, no network client, and no
clock or id generator it did not receive as an argument.

**Why.** The clinical logic is the part that has to be obviously correct. Keeping
it free of I/O means a red-flag rule can be tested in microseconds, the
evaluation harness can replay 22 patients without a database, and reviewing the
state machine does not require understanding the ORM.

**How it is held.** `tests/safety/test_no_auto_escalation.py::TestNoModelInTheLoop`
reads every file under `app/domain` and fails on a forbidden import, on
`datetime.now(`, on `uuid4(` and on `random.`. A convention would have decayed
inside a fortnight; the test does not.

**Cost.** Callers must supply `now` and every id. `app/core/clock.py` and
`app/core/ids.py` exist solely to hand them over, and the service layer is
slightly more verbose for it. Worth it: the whole system is reproducible.

---

## 2. Five statuses, and no boolean anywhere near them

`PRESENT | ABSENT | UNKNOWN | NOT_ASKED | NOT_APPLICABLE`.

**Why.** "We did not ask about allergies", "the patient denied any allergy" and
"the patient could not remember" are three different medico-legal positions. A
`bool` can hold one of them.

**Consequences that fall out of it.** `NOT_ASKED` is the default for an untouched
concept, so a concept nobody raised never reads as a negative. `UNKNOWN` counts
as *answered* for coverage — treating "I don't know" as a gap would send the
kiosk round in circles asking a question the patient cannot answer.
`NOT_APPLICABLE` shrinks the coverage denominator rather than counting as a
miss, so a male patient's pregnancy question does not depress his completeness
score.

**Rejected.** `Optional[bool]`, which collapses three of the five.

---

## 3. Facts are immutable; a correction is a new revision

`ClinicalFact` is a frozen dataclass. Corrections call `revise()`, producing a
new fact whose `supersedes` points at the old one. `clinical_facts` is
append-only and has no UPDATE path anywhere in the codebase.

**Why.** The audit trail is the product. A physician asking "what did they say
the first time?" must get an answer, and that is only possible if the first
answer still exists.

**Consequence.** `PatientIntakeState.apply` enforces the supersession chain:
superseding an unknown fact, or superseding a revision that is no longer live,
raises. That last check is a lost-update guard — two clients correcting the same
fact from the same stale read cannot both win silently.

---

## 4. Certainty may never increase, except by a human act

`revise()` raises `CertaintyIncreaseError` if the new certainty outranks the old.
The only paths that may raise it are `confirmed_by_patient` and
`verified_by_physician`, and both record who did it.

**Why.** `"maybe two weeks"` becoming `"2 weeks"` is the single most dangerous
silent transformation in a system like this, because the output looks better
than the input and nobody can see where the confidence came from.

**Where it bites.** `app/services/answers.py` caps certainty at `APPROXIMATE`
whenever the patient's words contain a hedge, in English or Hindi. A confirmation
of a hedged answer stays hedged: the patient re-affirmed a hedge, they did not
sharpen it.

**Also.** `patient_confirmed` and `physician_verified` are separate flags and
neither implies the other. A patient can be certain and wrong; a physician can
verify something the patient never confirmed.

---

## 5. The original expression is stored beside the normalised concept

Every fact carries `original_expression` and `original_language`.

**Why.** `"seene mein jalan"` is not `"burning chest pain"`. The normalisation
may be wrong, and a physician who can see the patient's own words can catch it.

**Where it shows up.** The rendered report prints the verbatim phrase after the
normalised line. `DeterministicFHIRMapper` puts it in `CodeableConcept.text`,
which is what that field is for — so the invariant survives the integration
boundary as well, which is where it matters most.

---

## 6. `SourceRef` points at a transcript span or a document region

Exactly one of `transcript`, `document`, `entered_by`, enforced in
`__post_init__`.

**Why.** This is what makes the physician report click-through-to-evidence, and
that feature is what earns clinical trust. Without it the report is an assertion;
with it, it is evidence.

**Consequence.** `GET /intakes/{id}/facts/{fact_id}/evidence` returns the
provenance plus the whole supersession chain, so the UI can show both the current
value and how it got there.

---

## 7. Clinical content lives in YAML, not in Python

Pathways, red-flag rules, review-of-systems groups, the Ayurveda module, the
concept registry and the consent notice are all files under `clinical/`.

**Why.** A Vaidya has to be able to review the questions and the criteria. If
they are in Python, that review does not happen — and the review is worth more
than the code.

**Consequence.** Loading is strict and fatal. A pathway that does not parse, a
rule with no `clinical_source`, a rule reading a concept no screen asks — each
stops the process at startup. A system that silently asks fewer safety questions
than it was configured to is worse than one that will not boot.

**Rejected.** A database table for content. It would have made the content
editable at runtime, and made it invisible in code review. A pull request
diffing `clinical/redflags/cardiac.yaml` is a clinical governance artefact.

---

## 8. One expression language for preconditions and red-flag criteria

`app/domain/ontology/expressions.py` parses `all` / `any` / `none` / `not` over
leaves like `{concept: severity, gte: 7}`, and both pathway preconditions and
red-flag rules use it.

**Why.** A clinician who learns to read one learns to read the other. Two
syntaxes would have meant two things to teach and two parsers to keep honest.

**Design note.** Evaluation is total: an unestablished concept makes a leaf false
rather than raising. A rule that cannot be evaluated has not fired. Unknown keys
are rejected at load time, so a misspelt `critera:` fails the build instead of
silently disabling a safety rule.

---

## 9. "Not applicable" means we know it does not apply

A field whose precondition fails is only recorded `NOT_APPLICABLE` once every
concept the precondition reads has been settled.

**Why this is here.** The first implementation marked a field inapplicable the
moment its gate evaluated false — which, at the start of an intake, is always,
because the gating concepts are still `NOT_ASKED`. Pregnancy is gated on sex and
age, so every woman was permanently ruled out of the pregnancy question before
she was asked her age. The evaluation harness caught it.

**The rule now.** An undecided precondition is not a failing one. The field
waits.

---

## 10. A red flag never touches the queue

`evaluate(state, rules) -> tuple[RedFlagAlert, ...]` and nothing else. Escalation
requires an acknowledged alert id *and* an acting user, and `ops.escalate`
rejects the call without both.

**Why.** Software moving a patient up a queue on its own reading of their answers
is a clinical decision made by a machine. A human acknowledging an alert is what
converts a criterion into an action, and the record has to name that human.

**How it is held structurally.** The red-flag package imports nothing from the
queue package, and a test asserts it. There is no code path between them to
review — there is no path at all.

**Wording.** Every alert label is the fixed string "Urgent clinical review
criterion triggered". Never a disease name, never addressed to the patient. A
test checks every shipped rule, so a well-meaning content edit cannot turn an
alert into a diagnosis.

**Tuning.** Rules are written for recall over precision. A false alert costs a
triage nurse thirty seconds; a missed emergency is not recoverable. The
`forbid_red_flags` scenarios in the evaluation corpus keep that from becoming an
excuse for a rule that fires on reflux.

---

## 11. Intake state and queue state are orthogonal, in the database too

`IntakeState` and `QueueState` are separate enums on separate tables, and
`tickets` has no intake-state column.

**Why.** `WAITING + IN_PROGRESS` is the normal, desirable state: a patient in the
queue part-way through their history. `CALLED + NOT_STARTED` must work — a
walk-in who never touched a kiosk still gets seen. Deriving either from the other
would break both cases.

**Consequence.** `PREFER_INTAKE_READY` needs to see intake readiness while
ordering tickets, so it receives it as a lookup argument rather than reading a
denormalised column. A cached copy on the ticket would have been the first place
the two drifted apart.

---

## 12. `PREFER_INTAKE_READY` is off by default and bounded three ways

Within the same priority class, within ±N positions, and capped per ticket by
`max_overtaken`.

**Why bounded.** The feature keeps a practitioner from idling on an unprepared
patient. Unbounded, it becomes a queue where the unprepared never get seen —
which in an OPD means the elderly, the illiterate and the people who came
without a smartphone.

**Why off by default.** Reordering a queue is a hospital policy decision, not a
software default. A facility turns it on deliberately.

**Visibility.** `overtaken_count` and `waiting_minutes` are on every dashboard
row. The guard is not merely enforced; it is watchable.

---

## 13. `call_next` locks one row, not the candidate set

Read the candidates unlocked, let the domain choose, then `SELECT … FOR UPDATE
SKIP LOCKED` the chosen row; on a miss, drop it and choose again.

**Why not lock the whole set.** That was the first implementation, and it was
safe but useless: the first caller locked every candidate row, so the second was
told the queue was empty. The concurrency test caught it.

**Why not push the ordering into SQL.** `ORDER BY … LIMIT 1 FOR UPDATE SKIP
LOCKED` would lock exactly one row in one statement, but the ordering policy —
priority class, appointment time, the intake-ready window, the starvation cap —
would then live in SQL where it cannot be unit-tested. Keeping the decision in
the pure domain is worth one extra round trip.

**Bounded.** The retry loop is capped at the candidate count, so a busy queue
cannot spin.

**Counters.** Passed-over tickets have `overtaken_count` incremented atomically
in SQL, not read-modify-written in Python. A lost increment there would weaken
the starvation guard, which is the one thing bounding the whole mechanism.

---

## 14. Documents never overwrite what the patient said

A fact read off a scan enters the live view only if the patient has not answered
that concept. Where they have, it is parked in `record_facts` — persisted with
`record_channel = true` — and both survive.

**Why.** The disagreement *is* the finding. Letting an OCR pass silently replace
a patient's denial would destroy exactly the thing that makes scanning the old
prescription worth doing.

**And the patient gets a say.** A document- or prior-record-sourced fact is not
treated as answered: the state machine puts it back as "our record shows X — is
that still correct?" rather than an open question. Asking a returning diabetic
"do you have diabetes?" reads as though the hospital lost their file.

**Consequence for the detector.** When a patient corrects a record fact, the
correction supersedes it — so the detector reads the full fact history, not just
the live view, and treats a record fact superseded by a patient answer as
evidence rather than as history. This was a bug the evaluation harness caught.

---

## 15. Contradictions are reported and never resolved

`Contradiction` holds both sides with their provenance and a fixed
`resolution: "Physician verification required"`.

**Why.** Choosing between two conflicting histories is a clinical act. The value
of surfacing a conflict is destroyed if software silently picks a winner, and
picking the higher-confidence side would be exactly the wrong heuristic — the
patient in front of you usually knows more than a two-year-old discharge summary,
and sometimes does not.

**Noise control.** Only clinically material concepts are watched, and `UNKNOWN`
never conflicts: a patient who cannot remember has not contradicted anything, and
flagging that would bury the real conflicts.

---

## 16. The summary is template-assembled, not generated

`app/domain/summary/builder.py` renders facts through string templates.

**Why.** A template cannot hallucinate a symptom, and its output is valid on its
own. A language-compression provider may later rewrite this prose, but only if
every sentence validates back against the same fact set — and the template output
stays the fallback.

**Two properties it buys.** Every rendered line carries the `fact_id` list it was
built from, so any statement links to its evidence. And anything not established
prints under **Unresolved** rather than vanishing: the difference between "no
allergies" and "we never got to allergies" is one a physician has to see.

**Checked.** `find_unsupported_assertions` scans rendered output for diagnostic
and advisory phrasing. The evaluation harness fails the build on any hit; the
target is zero.

**A distinction worth recording.** Prompts and output are checked against
different vocabularies. "Has a doctor ever told you that you have diabetes?" is
exactly how a past medical history is taken — the disease name and the words "you
have" are doing honest work. The same phrases in a generated report would be the
system asserting a diagnosis. So the prompt check bans advice and interpretation;
the output check bans those *and* second-person assertions and named conditions.

---

## 17. Logs are scrubbed by a filter, not by discipline

`app/core/logging.py` runs `phi_filter` last in the structlog pipeline. Denylisted
keys are redacted whatever their value; Indic script and long digit runs are
redacted whatever their key.

**Why the key-independent rules.** The key a leak arrives under is exactly the key
nobody thought of. A patient's own words in Devanagari, and a phone number, have
no legitimate place in an operational log under any name, so the allowlist does
not get a vote on them.

**Proof.** `tests/safety/test_logging_phi.py` writes eight kinds of clinical text
through the full pipeline and asserts none of it reaches the emitted record —
while asserting the identifiers needed to debug still do.

**Events too.** `Event.__post_init__` rejects a payload carrying a forbidden key.
These frames fan out to waiting-room displays; a display showing "KC-014" must
not be one bug away from showing why that patient is here.

---

## 18. Consent is a versioned artefact, not a boolean

`consent_artefacts` stores the exact notice text and its hash, the language, the
audio asset played, the purposes granted *and refused*, the granting party and
the timestamp. Immutable: a withdrawal writes a new artefact.

**Why.** DPDP Act 2023 requires that we can produce, for any patient, exactly
what they agreed to. A boolean cannot.

**Purpose separation.** Recording a patient's voice and *keeping* it are
different asks, so `raw_audio_retention` is its own purpose code, off by default,
and gated by both the facility setting and the patient's own grant.

**Refusal is a valid outcome.** Declining the base purpose abandons the intake
and returns 201, not an error. The patient sees the doctor without a kiosk
history, and their place in the queue is untouched — the consent notice says so
in both languages, and a test asserts the sentence is there.

---

## 19. Idempotency and revisions, both

`Idempotency-Key` replays the stored response; the intake `revision` rejects a
stale write.

**Why both.** The key handles the retry. The revision handles the reconnecting
kiosk that has a fresh key but an old view of the state — without it, a kiosk
coming back after a LAN drop could clobber a correction the patient made in the
meantime.

**A key reused with a different body is a 409**, not a stored-response replay.
That is a client bug, and serving the earlier response would return the wrong
answer to a different question.

---

## 20. Terminology matching is deterministic

Trigram similarity over a folded, transliterated form. No embeddings, no network.

**Why.** The same query returns the same ranked candidates on a kiosk with no
internet as in the cloud, and the evaluation harness cannot go flaky. An
embedding matcher is a later provider behind the same interface; it will rank
better and it still will not be allowed to invent a mapping.

**Where no mapping exists, none is returned.** A ConceptMap that invents a
correspondence between an Ayurvedic nosological entity and a biomedical code is
worse than an empty one, because it looks authoritative and ends up in someone's
discharge summary. `conceptmap.yaml` marks Madhumeha ↔ type 2 diabetes as
`inexact` and says why in a comment.

**Two bugs found here by tests.** Token normalisation was stripping Devanagari
matras, turning `"सीने में दर्द"` into `"स न म दर द"`. And transliteration was
dropping the inherent vowel, so `"संधिगत"` became `"sndhigt"` and never matched
`"sandhigata"`. Both are the kind of defect that would have looked like "search
is a bit weak" in a demo.

---

## 21. The Ayurveda module collects, it does not assess

`clinical/ayurveda/ayurveda_module.yaml` asks about Agni, Koshtha, Nidra, Mutra,
Sweda, Bala, Ahara and Vihara — all patient-reportable.

**What it deliberately does not do.** Prakriti determination. That is a clinical
act performed by the Vaidya through observation and examination; a kiosk cannot
do it, and a system that printed a Prakriti would be making exactly the kind of
claim this whole design exists to avoid.

---

## 22. Mock providers are scriptable, not random

`ScriptedExtractor` maps an utterance to facts by exact lookup and returns
nothing when the script has no entry.

**Why deliberately incapable of inference.** A mock that guessed would make the
end-to-end tests pass for the wrong reason. Returning nothing means the state
machine asks again, which is the correct behaviour for a system that must never
invent an answer — and it is what a real extractor should do when it is unsure.

**`TemplateQuestionRenderer` is not a mock.** It reads the prompt straight from
the pathway YAML and is the permanent offline production path for a kiosk with no
internet.

---

## 23. The evaluation harness is a deliverable

`evaluation/` is a first-class package with 22 scenarios, wired into pytest.

**Why it is not a test utility.** It is what converts "the system asks the right
questions" into a number someone can check. It found four real defects during
this build, three of which the unit tests did not: the premature
`NOT_APPLICABLE`, the unconfirmed document fact, and the vanishing contradiction.

**Two tests prove it can go red.** A green harness that cannot fail is worse than
no harness, because it is believed.

**One metric was redefined.** "Irrelevant questions per session" originally
counted questions the test script had no answer for — which measures script
completeness, and would improve as the scripts grew rather than as the system
did. It now counts questions from a complaint pathway other than the active one,
which is the claim actually being made.

---

## 24. What was deliberately not built

- **No message broker in the request path.** `InProcessBus` is what the
  single-node deployment runs. NATS is in the compose file for a multi-node
  hospital and is not required.
- **No cache layer.** Redis is optional and unused by the clinical path.
- **No CQRS, no event sourcing framework.** The fact log is append-only because
  the audit trail demands it, not because of a pattern.
- **No microservices.** The prevailing failure mode in a system like this is
  architectural over-decoration, and the strongest version is the one whose
  clinical logic is obviously correct.

## 25. Idempotency is applied per endpoint, not by middleware

Each mutating route wraps its work in `idempotent(guard, Model, produce)`.

**Why not middleware.** One middleware would have covered every route including
future ones, and it was the first design. It has to buffer the request body to
fingerprint it — which means buffering a multipart scan upload into memory, on
the one endpoint where the payload is a photograph of a prescription. The
per-endpoint helper is four lines a route and leaves the upload alone.

**How the requirement is held.** `tests/api/test_brief_completeness.py` walks the
generated OpenAPI schema and fails on any POST/PATCH/PUT that does not accept the
header. A route added later without a guard breaks the build.

**`call_next` is a special case.** A retry after a dropped response must not call
a *second* patient while the first is walking to the room, so it is guarded — but
a `None` result is deliberately not remembered, because "nothing to call" now
does not mean nothing to call in five minutes.

---

## 26. Known gaps

- **Authentication is a header stand-in.** `X-User-Id` / `X-User-Role` fail
  closed on an unknown role and the role checks are real, but real
  authentication is the hospital's identity provider and belongs in `deps.py`
  alone.
- **OCR runs inline in the upload endpoint.** The async worker is the design
  target; the entry point (`apply_document_extraction`) is already the one a
  worker would call.
- **`PubSubBus` raises `NotImplementedError`.** The protocol and wiring exist so
  the swap is a config change; nothing pretends to work.
- **The FHIR bundle is served but not pushed.** `GET /intakes/{id}/fhir` returns
  a dual-coded R4 Bundle; delivering it to a hospital HMIS is `HISAdapter` work
  and needs a real endpoint to integrate against.
- **Terminology seeds are placeholders.** Flagged in
  `docs/CLINICAL_REVIEW_QUEUE.md` and in the files themselves.
- **32 content items await clinician review**, listed in
  `docs/CLINICAL_REVIEW_QUEUE.md`.
