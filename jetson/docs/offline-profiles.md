# Offline profiles

The Raspberry Pi and Jetson variants reuse the deterministic clinical state machine, red-flag
rules, question templates, and encrypted SQLite store in this repository. Their speech stacks
must run as separate device-specific workers so large ML dependencies do not destabilize the
online service.

## Raspberry Pi 5

Run on 64-bit Raspberry Pi OS:

```bash
sudo apt update
sudo apt install -y cmake build-essential git ffmpeg libasound2-dev python3-venv
bash scripts/setup_pi_offline.sh
bash scripts/check_device_readiness.sh pi
```

The installer builds `whisper.cpp`, downloads the multilingual `base` model, quantizes it to
Q5_0, and creates an isolated environment for Silero VAD and DeepFilterNet. Piper is kept as a
separate voice install because the chosen Hindi/English voice license and quality must be
reviewed before distribution. Candidate Hindi voices in the Piper catalogue include
`hi_IN-pratham-medium` and `hi_IN-priyamvada-medium`.

Expected processing order:

`ALSA input -> WebRTC AEC -> DeepFilterNet -> Silero VAD -> whisper.cpp -> clinical core -> Piper`

WebRTC AEC needs both the microphone capture and the exact speaker reference stream. Merely
running a noise filter does not provide echo cancellation.

## Jetson Orin Nano

Run:

```bash
bash scripts/setup_jetson_offline.sh
bash scripts/check_device_readiness.sh jetson
```

The script prepares Silero ONNX and the native ARM64 DeepFilterNet binary, then pulls optional
`gemma3:1b` through the already
installed Ollama service. It deliberately avoids the `silero-vad` Python package on JetPack,
and avoids DeepFilterNet's Python wrapper, because their generic PyTorch dependencies can pull
an incompatible CUDA runtime. AI4Bharat
IndicConformer 600M and IndicF5 are not downloaded
automatically: their Hugging Face access/terms must first be accepted and `HF_TOKEN` must be set
on the Jetson. IndicF5 also requires a suitable reference voice clip and matching transcript;
that is a product/voice-consent decision, not a safe installer default.

Expected processing order:

`ALSA input -> WebRTC AEC -> Silero VAD -> IndicConformer -> clinical core -> Flite Indic TTS`

Keep Gemma optional and downstream of the deterministic question selector. It may rephrase a
selected question but must never choose urgency, invent clinical facts, or suppress a red flag.

## Jetson: what actually runs today

Nine languages, no network path. The loop is `medikiosk.edge.runtime`.

| Stage | Implementation | Measured |
|---|---|---|
| Capture | USB camera microphone (card 2) via PulseAudio | 16 kHz mono, 32 ms frames |
| AEC + noise suppression | PulseAudio `module-echo-cancel`, `aec_method=webrtc` | echo RMS 1471 -> 49 |
| VAD | Silero v5 ONNX, CPU | 576-sample window (64 context + 512) |
| ASR | **Whisper large-v3-turbo q5** (547 MB) on CUDA, resident in `whisper-server` | 1.1-1.9 s first turn, 0.72-0.85 s after |
| Language choice | detected from the opening turn, then locked | see below |
| Question choice | `ClinicalStateMachine` + per-language templates | deterministic |
| Safety | `evaluate_red_flags` | deterministic |
| TTS | **Pre-rendered MMS-TTS** for every fixed prompt, all nine languages; Piper (hi/en/te) and Flite (rest) still live for anything unrendered | 0.2 ms cache hit vs 0.22-0.48 s Piper, 0.28-0.36 s Flite |
| Playback | USB speaker (card 3) via the AEC sink | |
| Barge-in | playback killed on confirmed speech | ~460 ms from speech onset |
| Storage | Fernet-encrypted SQLite | 851 bytes per intake |

One multilingual model replaced the per-language Conformer checkpoints, which cost ~1.2 GB
resident each and could never have held nine languages on an 8 GB board. The old Hindi Conformer
also decoded against a truncated 88-entry vocabulary while the model emits 129 classes, which is
why it produced "जेन" for "दिन". The `bhashini_models` service is no longer used by the kiosk at
all: Whisper does ASR and the Flite binary is invoked directly. Stopping it frees ~3.6 GB.

### Language support, honestly

| Language | ASR | Prompt voice | Live fallback voice | End-to-end verified |
|---|---|---|---|---|
| Hindi | Whisper | MMS-rendered | Piper `hi_IN-pratham-medium` | yes, full intake |
| English | Whisper | MMS-rendered | Piper `en_US-lessac-medium` | yes, full intake incl. red flags |
| Telugu | Whisper | MMS-rendered | Piper `te_IN-maya-medium` | synthesis only |
| Bengali, Marathi, Tamil, Gujarati, Kannada, Punjabi | Whisper | MMS-rendered | Flite CMU Indic | synthesis only |

Every prompt the kiosk speaks offline is fixed before a patient arrives, so it is rendered once at
build time with MMS-TTS and served from disk. That is what lifted the six languages Piper cannot
voice to neural quality without putting six more models in the 8 GB budget. `medikiosk.kiosk.prompts`
is the single definition of that corpus, used by both the renderer and the runtime lookup so they
cannot drift.

Piper's Bengali and Marathi voices are installed but still unusable with the shipped binary
("aI is not a single codepoint"), and upstream ships the same broken files, so they remain the
live fallback only for text nobody pre-rendered. Piper is archived; there is no fix coming.

`scripts/benchmark_languages.py` round-trips a phrase through voice and ASR for all nine and now
reports CER and WER against the text that was spoken, optionally drawing its clips from the real
prompt corpus with a fixed seed. Mean CER on rendered audio: en 0.03, hi 0.16, ta 0.25, mr 0.34,
kn 0.46, bn 0.76, pa 0.88, gu 0.98.

**Those numbers still do not license an accuracy claim.** It is a TTS-to-ASR round trip, so bad
synthesis and bad recognition are confounded, and synthetic speech is cleaner than a patient in an
OPD. What the harness is good for is comparing two ASR models on identical clips - the rendered
audio is at least intelligible, which Flite was not: Kannada CER fell from 1.00 on Flite to
0.03-0.36 on the rendered audio, and that gap is the test voice, not the recogniser. The seven
unverified languages still need recorded human speech before any claim is made about them.

### Latency knobs that mattered

- **Pin the language after the first turn.** Whisper pads every clip to a 30 s window, and
  auto-detect costs an extra pass: pinning roughly halved turn latency. It also prevents a
  one-word answer, which carries almost no language evidence, from throwing the session into
  another language mid-interview.
- **`--audio-ctx 750`** (~15 s of context instead of 30 s) halved latency again with no change to
  the transcripts. At 500 words began corrupting, so 750 is the floor.
- **Keep Piper resident.** Invoking the binary per prompt reloaded its 63 MB model every time,
  about two seconds a turn. Fed a line at a time it stays loaded: first prompt 2.2 s, then 0.22 s.

Prompt biasing toward expected answers was tested and rejected: it produced no measurable gain,
and nudging a decoder toward "yes" is exactly the kind of certainty the kiosk must not manufacture.

### Two things that fail silently if you get them wrong

1. **`aec_args` must be quoted as one value.** `pactl` splits module arguments on whitespace, so
   an unquoted multi-value `aec_args` reaches the module as separate arguments and it fails to
   load with only `Failure: Module initialization failed`. Quote the value itself instead.
2. **Silero v5 needs a 64-sample context.** The ONNX graph takes 576 samples (64 context + 512
   frame). Feed it a bare 512-sample frame and it still runs, returning ~0.001 for speech and
   silence alike, so the kiosk simply never hears anyone.

### Levels are calibration, not defaults

Both ends have a floor and a ceiling, and both failures are real:

- Speaker at 100% clips the captured echo and AEC cannot remove it, so the kiosk transcribes its
  own question. Speaker far below 90% is inaudible to a patient.
- Mic at 30% (-66 dB) loses short words entirely: a spoken yes came back as an empty transcript.
  Mic high enough to clip transients destroys AEC linearity.

Current room settles at **speaker 90%, mic 60%**, verified with two consecutive echo passes and 0%
clipped ambient samples. `scripts/calibrate_audio.sh` sweeps the speaker from loud to quiet and
stops at the loudest level that passes twice; re-run it in the final enclosure.

One trap: the AEC sink's volume propagates to its master sink, so `medikiosk_speaker` must be set
*before* the master or the calibrated level is silently overwritten.

The USB camera microphone clips on transients once capture gain goes much above 65%, and it sits
close to the speaker, so a dedicated directional microphone placed away from the speaker remains
the recommended kiosk part.

### Running it

```bash
bash scripts/setup_jetson_audio.sh          # create medikiosk_mic / medikiosk_speaker
bash scripts/calibrate_audio.sh             # loudest speaker level that still passes echo
bash scripts/run_whisper_server.sh &        # resident ASR, ~30 s to load
python3 scripts/benchmark_languages.py      # voice -> ASR round trip for all nine
PYTHONPATH=src offline/jetson/audio-venv/bin/python -m medikiosk.edge.runtime
```

`scripts/simulate_intake.py` drives a scripted patient through a null sink: it exercises VAD,
segmentation, ASR, the state machine, the red-flag rules and TTS with nobody in the room. It
proves the logic, never the acoustics.

Autostart uses two systemd **user** units, `medikiosk-whisper` and `medikiosk-edge`, because the
echo-cancelled devices exist only inside the ubuntu user session.

### Translations are drafts

Questions, prompts, and the yes/no and number lexicons for all nine languages were written as
engineering drafts. **Each needs a native speaker and a clinician before patient use**: a question
that shifts meaning between languages silently changes what the record means. A test fails if any
language is missing any string, so gaps cannot ship silently - but correctness is not something a
test can check.

## Hardware acceptance test

Use the final mic, speaker, enclosure, room, and speaking distance. For each supported language:

1. Record silence, background noise, near speech, and far speech.
2. Play a TTS question while recording the mic and confirm the transcript does not contain the
   played question.
3. Interrupt TTS at several points and measure time from speech onset to playback stop.
4. Confirm the complete interrupted utterance reaches STT.
5. Exercise every deterministic emergency rule using synthetic/non-patient scripts.
6. Disconnect the internet and repeat the offline profile end to end.

Do not test emergency behavior with real patients until a clinician has approved the rules and
staff alert workflow.
