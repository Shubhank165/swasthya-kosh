# MediKiosk patient app

Touch-only pre-consultation intake, Flutter. Implementation 2 of 3.

The patient fills in the same intake from their phone that the kiosk's Jetson
collects by voice — by walking the same versioned question content and producing
the same versioned record.

## There is no voice capture in this app

No microphone permission, no speech-recognition package, and no UI element that
invites dictation into a clinical field. This is not a scope decision that could
be revisited: it is what preserves the project's privacy claim, which is that
**at the kiosk the patient's voice never leaves the device**. A second, weaker
voice path here — where audio would go to a cloud recogniser — would qualify
that into meaninglessness.

`test/no_voice_test.dart` asserts it on both platform manifests, on `pubspec.yaml`
and across `lib/`, because a dependency can add a permission to a merged Android
manifest without anyone editing a file in this repository.

`flutter_tts` **is** a dependency and is meant to be. It is text-to-*speech* —
output — for reading the consent notice aloud to a patient who cannot easily
read it (§11). Output is never input.

## Running it

```bash
flutter pub get
flutter gen-l10n
flutter run --dart-define=MEDIKIOSK_BASE_URL=http://10.0.2.2:8000
```

`10.0.2.2` is the host machine as seen from the Android emulator. Bring the
backend up first with `make dev` from the repository root.

### JDK

**Android builds need JDK 17 or 21.** Flutter picks the JDK bundled with Android
Studio by default, which on a current install is Java 25 — newer than this
project's Gradle understands, and the failure reads `Unsupported class file
major version 69`, which does not obviously mean "wrong Java".

```bash
flutter config --jdk-dir=/usr/lib/jvm/java-17-openjdk-amd64
```

That is a per-machine setting, not a repository one. Upgrading Gradle and AGP far
enough to accept Java 25 is the alternative and is a larger change than it looks;
Java 17 is the conventional target for AGP 8 regardless.

## Tests

```bash
flutter test
```

Host tests use the system SQLite (`test/test_sqlite.dart`) because
`sqlcipher_flutter_libs` ships the library to a device, not to a test runner. The
schema and every query are identical either way; what host tests do **not**
cover is encryption, which is asserted at runtime by the `cipher_version` check
in `LocalDatabase.open`.

## Layout

```
lib/
  content/     bundle model, cache, and the walker
  intake/      screens, and one widget per answer_type
  documents/   capture, quality check, EXIF strip, downscale
  identity/    sign-in, hospitals
  storage/     encrypted Drift database
  submit/      record assembly
  core/        config, http, theme, keystore, providers
  l10n/        nine ARB locales — UI chrome only
```

**`content/walker.dart` is the only file with clinical-ish logic in it, and it
must stay that way.** If a second file starts deciding what to ask or what
constitutes a red flag, the design has slipped: the point of downloading the
same content the Jetson walks is that there is one description of the interview,
not three implementations of it.

## What the app does not decide

- **Which questions exist**, and which follow which complaint — that is
  `clinical/questions/**`, authored by a clinician and compiled by the backend.
- **What is a red flag** — same file. The app evaluates the rules it is given;
  it does not contain them.
- **Anything diagnostic.** Nothing here names a condition, states a likelihood,
  or shows extracted OCR values back to the patient. The urgent-care screen
  tells a patient what to *do*, never what they have.

## The nine languages

The app's own chrome is translated into all nine and every ARB carries every key
(`test/l10n_completeness_test.dart`).

**The clinical question prompts are not.** They come from the bundle, which
advertises `en` and `hi` because that is what has been authored, and the backend
refuses to advertise a language it has no prompts for. Where the bundle has no
prompt in the patient's language the walker records `not_asked` rather than
falling back to English — a patient answering a question in a language they did
not choose produces a record saying they answered something they may not have
understood.

**All of these translations are engineering drafts** pending a native speaker and
a clinician. `docs/CLINICAL_REVIEW_QUEUE.md` lists them, with `answerDontKnow`
and `answerSkip` flagged highest-risk: they are UI strings whose *meaning* is
defined by the record contract, so a wrong translation produces a wrong clinical
status rather than an awkward phrase.
