# Assumptions made to close the clinical review queue

`docs/CLINICAL_REVIEW_QUEUE.md` is the agenda for an AIIA mentor / Vaidya
session that has not happened yet. This build needed every item to
have *some* answer so the system runs end to end and the demo does not stall
on an open question — so each item below was closed with an engineer's
judgment call rather than a clinician's, on the explicit understanding that
**this does not make any of it clinically validated.** The system's own
disclaimers (unverified, patient-reported, no diagnosis) are unaffected and
still hold regardless of anything in this file.

Each entry says what was decided, why, and exactly which file to edit to
change it — because the point of keeping clinical content in `clinical/**`
and out of Python/Dart is that a real review session should produce a content
diff, not a re-architecture. `docs/CLINICAL_REVIEW_QUEUE.md` now cross-links
back here; treat that file as the checklist and this one as the reasoning.

None of this touched `clinical/interactions/seed.yaml`'s sourcing, the report
status vocabulary, the tenancy/PHI/certainty guarantees, or anything else
`README.md`'s "What it refuses to do" table holds — those are enforced by
tests, not by clinical judgment, and are out of scope for this pass.

---

### A1 — App UI translations (8 non-English languages) shipped unreviewed

**`docs/CLINICAL_REVIEW_QUEUE.md` §1.** Accepted the existing
engineer-drafted `app/lib/l10n/app_*.arb` files as-is. No native speaker was
available. The five clinically-load-bearing strings (`answerDontKnow`,
`answerSkip`, `consentNotTranslated`, `skipForNow`, `optYes`/`optNo`) were
spot-checked by hand back-translating the Hindi (the only one I can partly
read) — they render as distinct, non-negative statements, matching intent.
The other seven languages were not spot-checked at all.

**One accepted risk:** in Hindi, `skipForNow` ("छोड़ें") and `answerSkip`
("यह प्रश्न छोड़ें") share the root verb — exactly the collision §1 warns
against. Left as-is because `skipForNow` only leaves the optional ABHA
screen; it cannot mis-record a clinical answer, so the failure mode is a
confused patient, not a corrupted record.

**To change:** edit `app/lib/l10n/app_<lang>.arb` directly — content only,
no code change, `app/test/l10n_completeness_test.dart` will still pass as
long as every key stays present. To fix the collision specifically, give
`skipForNow` a distinct verb (e.g. "अभी नहीं" — "not now") in `app_hi.arb`.

### A2 — Urgent-care wording accepted as drafted

**§1**, `urgentTitle`/`urgentBody`/`urgentAction`. Kept as written — reads as
an instruction to act now, names no condition. Not independently verified
for the indigenous-script languages beyond Hindi, per A1.

**To change:** same files as A1.

### A3 — Emergency number: global default `108`, per-hospital override left unwired

**§1**, last bullet. `108` stays the only value used. While tracing this I
found that `AppConfig.withEmergencyNumber` (`app/lib/core/config.dart`) — the
mechanism the code comments say exists for a per-hospital number — is never
called from anywhere, and `HospitalRecord` (`backend/app/models/clinical.py`)
has no `emergency_number` column to call it *with*. The plumbing on the app
side is real; the backend field and the wiring between them do not exist.
Fine for a single-hospital demo; not fine for a second deployment in a state
where 108 is wrong.

**To change:** add an `emergency_number` column to `HospitalRecord`, return
it from the hospital-lookup endpoint the app already calls, and call
`config.withEmergencyNumber(hospital.emergencyNumber)` when that response
arrives (`app/lib/intake/intake_host.dart` reads `configProvider` today and
is the natural place to fold it in).

### A4 — Question prompts stay English + Hindi only

**§2.** No new language authored for this pass. `not_asked` for a patient
who picked one of the other seven languages stays the recorded behaviour
(already implemented, already the safer of the two options the queue names).

**To change:** authoring a new language is a content-only addition — a new
`clinical/questioning/vocabulary/<lang>.yaml` and
`clinical/questioning/localization/questions_<lang>.json`, following the
shape of an existing pair. The engine and the compiler
(`backend/app/questioning_agent/output/bundle.py`) already support N
languages; nothing in Python changes.

### A5 — Hindi report wording (36 strings) accepted as drafted

**§3.** Spot-checked `not_established`, `declined_to_answer`,
`not_applicable` and `unresolved_title` in
`clinical/report_templates/hi/report.yaml` — four visibly different,
non-negative statements, matching the English file's intent. Section
headings not checked against actual AYUSH OPD usage.

**To change:** edit `clinical/report_templates/hi/report.yaml` directly. A
changed string will fail `tests/report/test_determinism.py`'s golden file on
first run by design — regenerate and accept the diff (see `README.md`).

### A6 — Dashboard Hindi interface strings (170 strings) accepted as drafted

**§3a.** Spot-checked the six flagged keys in
`dashboard/src/i18n/strings.ts` — `verify.reject`/`rejectWarning` correctly
say "never established," not "no"; `alerts.acknowledge` vs `alerts.escalate`
read as different acts; `report.draft`/`report.unresolved` read as intended.
The remaining ~160 strings were not individually checked.

**To change:** edit `dashboard/src/i18n/strings.ts`; the missing-key and
no-stray-English tests catch structural drift, not wording quality.

### A7 — Drug–drug interaction table (20 rules) kept as-is

**§4.** No rows added or removed, no severities changed. Accepted the
WHO Model Formulary 2008 / CDSCO National Formulary sourcing already in the
file as sufficient for a demo of AYUSH OPD patients who may be on
allopathic medication concurrently.

**To change:** add a row to `clinical/interactions/seed.yaml` with a
`source:` field — the loader refuses a row without one.

### A8 — Ingredient aliases (32 entries) kept as-is

**§5.** Accepted the existing brand list as a reasonable, non-exhaustive
Indian-OPD subset. A missing alias fails silently safe (no flag raised)
rather than falsely, which is the documented intended failure direction.

**To change:** add entries to `clinical/interactions/ingredients.yaml`.

### A9 — Flagged concepts (4 of 103) wording kept, review flag left `true`

**§6.** `abdominal_rigidity`, `thunderclap_onset`, `menstrual_history`,
`ritu_seasonal_variation` — wording accepted as displayed. `needs_clinical_review:
true` was deliberately **not** cleared on any of them: leaving it true keeps
the registry honestly reporting these as unreviewed rather than having an
engineering judgment call masquerade as clinical sign-off.

**To change:** edit `clinical/terminology/concepts.yaml`; flip the flag to
`false` only after an actual clinician reviews the entry.

### A10 — Terminology seeds: not resolved, and cannot be from here

**§7.** Explicitly out of scope for this pass, same as the doc already
says — replacing `namaste_seed.yaml` / `icd11_tm2_seed.yaml` /
`icd11_mms_seed.yaml` / `conceptmap.yaml` with the licensed NAMASTE/ICD-11
releases is a procurement task, not a judgment call an engineer or an
assistant can make. Shipping the curated seed data as-is; it is clearly
labeled as a seed and does not claim completeness.

**To change:** obtain the licensed releases and load them through the full
loader already written for this purpose, `app/services/terminology.py` — no
schema change needed, only data.

### A11 — Consent notice shipped as drafted, legal-review label kept

**§8.** Shipping `clinical/consent/consent_v1.yaml` as-is:
- `clinical_source` still says *"pending institutional legal review"* —
  left in place rather than cleared, because no legal review happened.
- `raw_audio_retention`'s `applies_to: [kiosk]` (omitted from the app) kept
  — the reasoning in the file (avoid filing a consent artefact for audio the
  app cannot capture) holds regardless of clinician input.
- Notice stays English + Hindi only, consistent with A4 — seven languages
  still stop at the consent screen, which is the documented safe failure.

**To change:** edit `clinical/consent/consent_v1.yaml`. Because consent
versions are immutable once granted, add a new `version: 2` block rather
than editing `version: 1` in place if any consent has already been recorded
under it.

### A12 — Carried-forward provenance: "confirmed today," not "re-asked"

**§8a.** Kept the current design: a returning patient sees "is this still
correct?" per carried field (`confirmed_today: true`/`false`/`null`), rather
than being asked the original question again. Simpler to demo, and the
schema (`backend/app/contracts/kiosk/v0_2.py`,
`backend/app/domain/record.py`) already supports the alternative without a
breaking change if a clinician later prefers it. Per-item granularity (one
row per carried fact, not one blanket "everything still correct?") kept as
implemented.

**To change:** switching to "re-asked" would mean screen 5 presents the
original question again instead of a yes/no, and sets `confirmed_today`
based on whether the new answer matches the carried one — a Flutter-side
change in the returning-patient flow
(`app/lib/identity/history_repository.dart` and the screen that consumes it),
not a contract change.

### A13 — Ayurveda current-state subset: three fields, no interval check

**§8b.** Kept the mapping exactly as inferred from the brief's wording —
`agni_appetite`, `nidra_sleep`, `koshtha_bowel` — and did **not** add
`mutra_urine` or `sweda_perspiration`, though the queue itself notes a
Vaidya may want them. Also kept: no check on how long ago the previous visit
was. A patient returning after two years gets the same three-field subset as
one returning after two days.

**To change:** field list — toggle `current_state: true` in
`clinical/questions/ayurveda/ayurveda_module.yaml`, content-only. Interval —
would need a "days since last visit" gate wherever screen 5 decides
first-visit vs. returning (the returning-patient check in
`app/lib/identity/history_repository.dart`), falling back to the full module
past some threshold.

### A14 — Document blur threshold kept at `800.0`

**§9.** Not a clinical judgment but has a clinical consequence, and there
was no corpus of real OPD photographs to calibrate against here either. Kept
the existing default, which is already documented as erring toward
acceptance (a false "too blurry" costs a patient a re-photograph they likely
won't do).

**To change:** `blurThreshold` in `app/lib/documents/prepare.dart`.
Recalibrate against real prescription photographs taken under OPD lighting;
the file's own comment gives the synthetic reference points (~11000 sharp,
~250 blurred) to compare a real corpus against.

---

## If this goes past the prototype

Read `docs/CLINICAL_REVIEW_QUEUE.md` with an actual Vaidya / AIIA mentor and
treat every "kept as-is" above as reopened, not settled. The fastest way to
audit what changed here versus what was already in the repo is `git log
--follow` on `docs/CLINICAL_REVIEW_QUEUE.md` and this file's own commit.
