# Question content

**This is a contract between three parties.** The Jetson at the kiosk walks it to
conduct a spoken interview; the patient app walks it to render a touch form; the
backend compiles it into the bundle both of them download. All three must agree
on what `chest_pain.severity` means, or the same field id arrives carrying two
different questions' answers.

It lived in `backend/stale/questionnaires/` for one build, moved there on the
reasoning that "question content belongs to the device that asks the questions".
That was right when the Jetson was the only asker. The patient app is a second
one, and a second copy of this content — or a Dart reimplementation of it — is
the drift problem the whole design exists to avoid. So it comes back, as shared
content rather than as an engine.

**The engine did not come back.** Nothing here is executed by the backend. It is
parsed, validated and compiled into a bundle, and that is all — `app/domain/
questions/bundle.py` is a compiler with no evaluation in it. Question selection
and red-flag evaluation still happen on the device that is asking.

```
pathways/
  core_intake.yaml       asked for every patient: identity, consent, chief
                         complaint, past history, medications, allergies,
                         family, personal history
  chest_pain.yaml        one per complaint — the HPI limb, matched on
  abdominal_pain.yaml    `matches_concepts`
  fever.yaml
  headache.yaml
  joint_pain.yaml
  general_follow_up.yaml
  screens/               the red-flag screen for each complaint. These are the
                         questions whose answers the rules in redflags/ read
  ros/                   review-of-systems groups, pulled in by a pathway's
                         `review_of_systems` list
ayurveda/                patient-reportable Ayurveda only. Deliberately NOT a
                         Prakriti assessment — that is a clinical act performed
                         by the Vaidya, and a kiosk claiming to do it would be
                         exactly the overreach this project refuses
redflags/                the rules. Every rule carries a `clinical_source`, and
                         a rule without one fails to load
```

## Rules for editing

- **`concept` is the field id that reaches the record.** Renaming one is a
  breaking change to the bundle contract and to every stored record that used
  it. Bump `content_version`.
- **Every field needs `prompts` in every language the bundle advertises.** The
  compiler fails on a missing prompt rather than falling back to English,
  because a silent fallback means a patient answering an English question they
  did not understand.
- **Preconditions and red-flag criteria share one expression language**:
  `all` / `any` / `not` over leaves of `{concept, status|in|gte|lte|equals}`.
  One language, so a reviewer learns it once.
- **A red-flag rule is tuned for recall, not precision.** Over-alerting is
  tuned down with clinicians once there is OPD data; a missed emergency is not
  recoverable.
- **Nothing here may state a diagnosis or give advice**, in any language. The
  red-flag `label` is fixed wording that says a human must look now, and never
  what is wrong.

## Review status

Every file carries a `clinical_source`, and most of them say *pending AIIA
mentor review*. `docs/CLINICAL_REVIEW_QUEUE.md` collects them. The Hindi
prompts in particular are engineering drafts: a question that shifts meaning
between languages silently changes what the record means, and no test can
catch that.
