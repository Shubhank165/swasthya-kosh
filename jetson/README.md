# MediKiosk Voice Intake

Safety-first multilingual intake prototype with one shared clinical core and pluggable online,
Raspberry Pi, and Jetson speech/model providers.

The runnable first slice is the online path:

1. A browser captures the microphone with WebRTC echo cancellation, noise suppression, and
   automatic gain control.
2. It downsamples audio to 16 kHz mono LINEAR16 and streams 100 ms chunks to the Jetson over
   WebSocket.
3. The Jetson proxies audio to Sarvam `saaras:v3-realtime` and receives partial transcripts,
   final transcripts, detected language, and VAD events.
4. OpenAI `gpt-5.6-terra` extracts only explicitly stated facts into a strict schema.
5. A deterministic state machine evaluates auditable red-flag rules and selects the next
   missing field.
6. `gpt-5.6-terra` rewrites only that selected question into patient-friendly language.
7. Sarvam `bulbul:v3` streams 24 kHz LINEAR16 audio back to the browser.
8. Local browser VAD or Saaras VAD stops playback on barge-in; new speech continues to STT.

This is an intake aid, not a diagnostic or treatment system. A clinician must validate its
questions, red-flag coverage, language behavior, and deployment workflow before patient use.

For detailed architecture diagrams, stage state machines, and multimodal edge pipelines, see [`docs/TECHNICAL_APPROACH.md`](docs/TECHNICAL_APPROACH.md).

## Local development

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
cp .env.example .env
.venv/bin/pytest
.venv/bin/uvicorn medikiosk.app:app --reload
```

On Windows, activate with `.venv\\Scripts\\Activate.ps1` or invoke the executables inside
`.venv\\Scripts` directly.

Without keys, the UI still accepts typed transcripts and runs the deterministic demo extractor.
With `OPENAI_API_KEY`, typed turns use GPT-5.6 Terra. Microphone STT and TTS require
`SARVAM_API_KEY`.

## Secret handling

Create `.env` on the machine running the backend:

```dotenv
OPENAI_API_KEY=...
SARVAM_API_KEY=...
SESSION_ENCRYPTION_KEY=...
```

Generate the storage key after installation:

```bash
.venv/bin/python -m medikiosk.keygen
```

Paste the generated value into `.env`. The SQLite database stores encrypted patient-state
payloads only. If `SESSION_ENCRYPTION_KEY` is absent, persistence is disabled rather than writing
clinical state in plaintext.

## Jetson deployment

Copy the repository to `/home/ubuntu/medikiosk`, then on the Jetson:

```bash
cd /home/ubuntu/medikiosk
bash scripts/install_jetson.sh
cp .env.example .env
nano .env
mkdir -p data
sudo cp deploy/medikiosk.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now medikiosk
curl http://127.0.0.1:8000/health
```

Browser microphone access requires HTTPS. Publish the loopback service privately through the
tailnet:

```bash
sudo tailscale serve --bg http://127.0.0.1:8000
tailscale serve status
```

Open the HTTPS URL printed by `tailscale serve status` from a tailnet device. Do not use Funnel;
the kiosk prototype should not be public on the internet.

## Ayush Prakriti questionnaire

The kiosk administers the CCRAS Prakriti Assessment Scale (Ministry of Ayush, 2nd ed. 2020) - all
58 items - and reports one of the seven classical Prakriti. It is asked once in a lifetime and
keyed to the patient's ABHA number, so a returning patient is never asked again; someone who says
they filled it elsewhere is believed rather than made to prove it.

This is separate from `kiosk/ayurveda.py`, which is Dashavidha Pariksha - the ten-fold examination
that describes the patient *today* and is asked every visit. Seven Prakriti, ten-fold examination:
different instruments, both on the vaidya's sheet.

**The scoring weights have not been reviewed by a vaidya.** CCRAS publishes its complete
item-to-dosha table only in the printed manual, which is copyright and released to assessors who
have completed CCRAS training. Six scoring rules across five items are stated outright in the
public preview and are used verbatim, marked `official=True`; every other weight is derived from
the classical references the manual itself cites and is marked `official=False`. Every record carries `scoring_reviewed: False` and prints
as provisional. Correcting the weights means editing one flat table in
`src/medikiosk/kiosk/prakriti.py` - they are kept that way for exactly this reason.

Sixteen items ask the patient about something CCRAS has an assessor observe, palpate, or test with
printed cards. They score like any other answer, and `summarize()` lists them under
`self_reported` so a doubtful Prakriti can be re-examined at those items. Built and height stay
outstanding: the scale measures them with a weighing scale and a stadiometer.

## Test levels

- `pytest`: clinical state, question order, red flags, encrypted storage, and HTTP smoke tests.
- Typed UI transcript: exercises OpenAI extraction/state/question wording without audio.
- Live microphone: exercises WebRTC capture, WebSocket transport, Saaras, barge-in, and Bulbul.
- Hardware acceptance: repeat with the intended directional microphone and speaker in the actual
  kiosk enclosure, because acoustic performance cannot be validated from software alone.

## Offline device preparation

Device-specific preparation and an acoustic acceptance checklist are in
[`docs/offline-profiles.md`](docs/offline-profiles.md). The scripts deliberately keep the large
offline model environments separate from the online server.

### Pre-rendered prompt audio

Every line the kiosk speaks offline is known before a patient arrives, so it is synthesized once
at build time rather than per turn:

```bash
offline/jetson/audio-venv/bin/python scripts/prerender_prompts.py
```

This writes ~1000 WAVs (~130 MB) under `offline/audio/`, which is gitignored - re-run it after
adding or editing any prompt, and it skips whatever is already on disk. Piper can only voice
Hindi, English and Telugu on this board, so the remaining six languages are rendered with MMS-TTS;
without this step they fall back to Flite, a 1990s formant synthesizer. The live engines stay
wired up for any text nobody rendered.

## Current platform status

- **Online:** implemented behind Sarvam and OpenAI provider adapters.
- **Raspberry Pi 5 offline:** Whisper.cpp Base Multilingual Q5, DeepFilterNet, and Silero setup is
  scripted; Piper voice selection and the realtime worker remain hardware acceptance work.
- **Jetson offline:** implemented and verified on the device - USB microphone through PulseAudio
  WebRTC echo cancellation, Silero v5 VAD, Whisper large-v3-turbo on CUDA covering nine languages
  with automatic language detection, the shared deterministic clinical core, pre-rendered MMS
  neural prompt audio for all nine languages with Piper and Flite as the live fallback, barge-in,
  and Fernet-encrypted local storage, with no network path. Hindi and English are verified end to
  end; the other seven languages need recorded human speech before any accuracy claim. See
  [`docs/offline-profiles.md`](docs/offline-profiles.md).
