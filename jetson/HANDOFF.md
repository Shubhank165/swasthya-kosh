# MediKiosk — handoff

Offline-first multilingual clinical intake kiosk. Jetson Orin Nano 8GB + Android tablet.
Everything runs on-device: no cloud calls, no API keys, no internet at demo time.

## What runs where

```
Tablet (Kivy APK)          Jetson Orin Nano
─────────────────          ─────────────────────────────────────────
display + touch            FastAPI  :8000   flow, clinical logic, OCR
mic (AudioRecord)   ←──→   MJPEG    :8800   rendered kiosk screens
speaker (audiostream)      whisper.cpp :11500   STT (CUDA)
camera                     Ollama   :11434   gemma3:1b, open-vocab extraction
                           pre-rendered WAV  TTS, 9 languages (MMS at build
                           Piper / Flite     time; live engines as fallback)
```

Linked by USB tethering. The tablet is the Jetson's screen and its microphone; every decision
is made on the Jetson.

## The 9-step flow

`src/medikiosk/kiosk/flow.py` sequences it; it owns no clinical logic.

1. **Language** — 9 languages, touch
2. **ABHA** — QR scan or typed; past visits from a local encrypted store (no ABDM network call)
3. **Who** — patient or proxy
4/5. **Interview** — spoken, multilingual. `ClinicalStateMachine` picks questions,
   `HybridClinicalExtractor` pulls facts (regex first, local LLM fills gaps)
6. **Ayurveda** — Dashavidha Pariksha, deterministic tally, asked every visit
7. **Prakriti** — the 58-item Ayush (CCRAS) scale, asked once in a lifetime and keyed to ABHA;
   opens by asking whether the patient has ever filled it. Reports one of the seven classical
   Prakriti. Scoring weights are provisional — see README.
8. **Documents** — camera → PP-OCRv5 Devanagari on-device
9. **Report** — findings, differential (ICD-10), FHIR R4 bundle, specialist queue

Red flags short-circuit to EMERGENCY from any stage.

## Rules that must not be broken

These are safety properties, not style preferences. Each has a regression test.

- **Triage is deterministic.** `clinical/red_flags.py` alone decides emergencies. No model
  output promotes or suppresses an alert.
- **The LLM never sets `severity`.** gemma3 invents scores from adjectives ("a bad headache"
  → 10). Severity feeds two red-flag thresholds, so it is heuristic/direct-answer only.
  See `clinical/hybrid.py`.
- **Speech outside the interview stage is dropped.** Otherwise a patient's "Namaste" at the
  language screen became a chief complaint of "ear pain".
- **Denials on select-type engine nodes are dropped, not scored.** `normalise_answer` returns
  YES for any non-empty value on SINGLE_SELECT, so passing `False` would score a patient who
  denied fever as having it. See `kiosk/differential.py`.
- **The differential is uncalibrated below ~5 findings** and says so in its own payload. The
  engine expects ~12 entropy-selected questions; the voice interview gives it 3–5.
- **ABHA numbers are stored as a salted hash**, visit bodies Fernet-encrypted, and only the
  last 4 digits ever appear in a report.

## Running it

```bash
# Jetson
PYTHONPATH=src python -m pytest                      # full suite
MEDIKIOSK_HOST=<usb-ip> PANEL_ENABLED=true PANEL_TARGET=tablet ./scripts/kiosk web

# Tablet APK (build on Linux/WSL with a JDK; first build pulls ~6GB of SDK/NDK)
cd tablet_app && ./build_apk.sh
```

`tablet_app/buildozer.spec` and `build_apk.sh` document three toolchain traps that cost hours:
p4a master builds Python 3.14 which Kivy cannot compile against (pinned to v2024.01.21),
`sdkmanager` needs an explicit `--sdk_root`, and WSL's inherited Windows PATH breaks buildozer's
subprocess quoting.

## Not in this zip, deliberately

- **Models** (~3GB): whisper GGUF, Piper voices, Silero VAD, PP-OCRv5 ONNX. Fetch separately.
- **Patient data**: OCR test photos are real people's prescriptions; the session and visit
  databases hold real intake text. Neither belongs in a file that gets emailed.
- **`.env`**: contains the Fernet key. `.env.example` shows the shape.

## Known open items

- **Camera scan (ABHA + documents) is unverified on the tablet.** Kivy's Android camera
  provider is the least reliable part of the stack. The app reports failures to the Jetson log
  (`client` events) rather than failing silently. If it never initialises, the fix is the one
  already applied to the microphone: use Android's own API via pyjnius instead of Kivy's wrapper.
- **The engine's 184 prompts are English-only.** Its 12 clinician-grade triage questions and
  entropy-driven question selection are therefore unused — the kiosk speaks 9 languages and must
  not switch to English. Using them needs translated clinical text, reviewed by a human.
- **Ayurveda: Sara, Samhanana and Pramana are reported as pending.** A kiosk with no scale and
  no stadiometer cannot assess them, so they are not guessed at.
- **Prakriti scoring is unreviewed.** CCRAS publishes its item-to-dosha table only in the printed
  manual, which is copyright and training-gated. Six scoring rules from its public preview are
  used verbatim; every other weight is reconstructed from the classical references it cites. Records
  carry `scoring_reviewed: False` and print as provisional. A vaidya must sign the `ITEMS` table
  in `kiosk/prakriti.py` before the Prakriti is presented as a finding.
- **Sixteen Prakriti items are self-reported.** CCRAS has an assessor observe or card-test them;
  the kiosk asks the patient instead and labels each one. Weaker evidence, recorded as such.
- **The tablet's registration and hub screens are client-side.** They have no server stage behind
  them, so the client walks the server forward to the stage it needs and then hands back. Two
  owners of one flow is a standing hazard: the symptoms pathway silently failed to start the
  interview once already.
