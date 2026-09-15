# The questioning agent

A deterministic adaptive history-taking engine. It replaces the fixed question
plan that stages 1 and 2 were going to shrink, and it replaces it rather than
shrinking it because the problem was never the length of the list — it was that
there *was* a list.

**It does not diagnose, and it does not need to.** There is no disease model in
here, no symptom→disease mapping and no classifier. The thing being optimised is
how much clinically useful history a practitioner has when the patient walks in,
per question the patient had to answer.

---

## What it replaces

`IntakeWalker` (Dart) and `clinical/questions/pathways/` walk a **fixed plan**:
a list of question ids, in order, each with an optional precondition. Every
patient gets the same 39 core questions, then the ~13 for their complaint, then
the Ayurveda module — around 70 questions, in the same order, whether they came
in with a cough or a broken toe.

That design has three faults, and they are structural rather than a matter of
tuning:

1. **The order is authored, not derived.** Nothing in the content says *why*
   `family_diabetes` comes before `pain_character`, so nothing can decide to
   skip it for a patient with a two-day cough.
2. **A question is a question.** There is no notion of the *information* behind
   it, so "when did the fever start" and "when did the headache start" are two
   unrelated entries and must both be asked.
3. **Answers are options.** A patient who types "since about Tuesday" into a
   duration question has said something the walker cannot use.

---

## The shape

```
CASE SCHEMA
    ↓
INFORMATION SLOTS        what a practitioner needs to know
    ↓
QUESTION BANK            ways of finding it out
    ↓
DEPENDENCIES             when a question makes sense
    ↓
SELECTOR                 deterministic scoring, one question at a time
    ↓
PATIENT RESPONSE         options, or ordinary language
    ↓
INTERPRETER              deterministic parsing into slots
    ↓
PATIENT STATE            the single source of truth
    ↓
(loop)
    ↓
CASE SUMMARY             for the practitioner
```

The unit of the system is the **information slot**, not the question. A slot is
one clinically useful fact — `fever.duration`, `headache.character`,
`digestion.after_eating`. Questions are how slots get filled, several slots at a
time where possible, and the selector chooses questions by what they would tell
somebody who does not know it yet.

That inversion is what makes everything else work. Merging three onset questions
into one is not a special case; it falls out of a question that extracts
`*.onset` across the active domains scoring higher than three that each extract
one.

---

## Determinism

**No model, anywhere in the runtime.** Not for selecting a question, not for
reading an answer. No LLM, no embeddings, no semantic search, no API call. The
same patient state and the same response always produce the same next question,
and the reason is inspectable:

```
QuestionDecision(
    question_id="bleeding.location",
    score=26.4,
    reasons=["bleeding is an active domain",
             "bleeding.location is unknown",
             "priority 8", "not previously asked"],
)
```

The scoring function is a weighted sum with named, configurable coefficients. It
is arithmetic somebody can check on paper.

Answer interpretation is dictionaries, regular expressions and rules: synonym
tables, unit normalisation, negation scopes, temporal patterns. Where the rules
do not reach, the interpreter says so — an uncertain fact is `UNKNOWN` with a
clarification question behind it, never a guess. **Confidence below the floor is
not an answer.**

This is not a limitation to work around later. A clinical record assembled by a
model is a clinical record nobody can audit, and every part of this project that
touches a fact — the five statuses, `original_text`, the certainty rules — is
built on being able to say where a value came from.

---

## AYUSH, and what a patient can actually answer

The case schema carries ordinary history — complaint, onset, duration,
progression, severity, character, aggravating and relieving factors, associated
symptoms, past history, medication, allergies — and the AYUSH-relevant history a
practitioner takes: diet, appetite, digestion, bowel habit, urine, sleep, daily
routine, activity, environment.

**Patient-observable and clinician-assessed are different things**, and the slot
registry marks which is which. A patient can say what happens after they eat.
They cannot report their own *agni*, and asking them to is asking them to
perform an assessment that is the practitioner's to make from the answers. So:

```
ask     "What do you usually feel after eating a full meal?"
never   "Is your agni mandagni or tikshnagni?"
```

The case summary is where specialist terminology appears, and even there it
labels what is patient-reported, what the system normalised, and what is left
for the clinician. Slots marked `patient_observable: false` are part of the
schema — the practitioner fills them in — and the engine never asks them.

---

## The first three questions are fixed

Routing, before anything adaptive:

1. **What is troubling you?** — multi-select over problem areas. Sets the active
   domains, and every later question hangs off them.
2. **Which of those is worst?** — the chief complaint, which weights everything
   after it.
3. **When did it start, and how has it changed?** — onset, duration and
   progression for the whole episode in one structured answer.

After those three the selector takes over. Nothing before them is adaptive,
because there is nothing to adapt to.

---

## Layout

```
backend/app/questioning_agent/      the engine. Imports nothing from `app/`.
    core/         state, schemas, enums
    knowledge/    the registries, loaded from clinical content
    questioning/  candidates, dependencies, scoring, selection, merging
    interpretation/  the deterministic parsers
    localization/ language-independent ids, language-specific text and vocabulary
    safety/       red flags, kept away from ranking
    output/       the case summary

clinical/questioning/               the content, reviewable like the rest
    slots.yaml
    questions/*.yaml
    vocabulary/<lang>.yaml
    localization/questions_<lang>.json
```

The engine is a library with no FastAPI, no database and no I/O of its own. It
takes a state and a response and returns a state and a question. That is what
makes it testable, and it is what will let it run behind an API, inside the
kiosk, or compiled into a bundle the phone walks offline.

**The offline question is open and is called out here rather than buried.** The
patient app runs its interview entirely on-device today, which is what makes the
kiosk work when the venue wifi does not. A Python engine reached over HTTP does
not have that property. Three ways out — compile a decision plan per turn and
ship it, port the selector to Dart, or accept that the phone app needs a
connection while the kiosk keeps its own engine — and the choice is a product
decision, not this document's. Nothing here forecloses any of them: the engine
is pure, so it can be called, ported or precompiled.

---

## Safety is separate

Red-flag detection does not live in the scoring function. A rule that fires
stops the questionnaire; it does not merely outrank the other questions. Mixing
the two would make an emergency a matter of coefficients, and the whole point of
that path is that it is not negotiable.

The rules say a human must look now. They do not name a condition, they are not
shown to the patient as a finding, and they are tuned for recall.

---

## Nine languages, generated with the code

Question identity and question text are separate. `question_id`, slot ids,
domain ids, option ids, dependencies, scoring and answer types are the same in
every language; only presentation changes.

Every supported language gets a complete bank — natural patient-facing phrasing
rather than word-for-word translation, the same clinical meaning, the same
option ids. A consistency test fails the build on a missing id, an English
string sitting in another language's file, or a placeholder.

Each language also gets its own normalisation layer: yes/no, negation,
temporal expressions, numerals, severity, frequency and symptom synonyms in the
words patients actually use. **The English parser is not assumed to work on
Hindi.**

These translations are engineer-generated and marked as such in the review
queue, like every other piece of clinical content here. That is a lower bar than
a clinician's sign-off and a much higher one than an English string with a
`TODO` next to it.
