# Demo video — the live loop

**What this video is for.** Your teammate's video shows the app. This one shows
the thing a screen recording of one device cannot: a patient finishes an intake
on a phone or a kiosk, the record travels to a backend running on Google Cloud
in Mumbai, is validated, screened and filed there, and appears on a doctor's
dashboard **without anybody pressing refresh**.

Target length **4–5 minutes**. Nothing in the script needs editing tricks; every
number on screen is produced live.

---

## Before you record

### 1. The deploy is done. Here is what is live.

`https://medikiosk-api-tjynzes4vq-el.a.run.app`, revision `8b0193a`, verified
after deploying:

| What | Status |
|---|---|
| Hospital | Sanjeevani Multi-Specialty Hospital, New Delhi |
| Departments | the nine general specialties |
| `X-User-Role: receptionist` | 200 |
| `X-User-Role: chemist` | 200 on `/pharmacy/*`, 403 on the worklist |
| `/ws/worklist` | connects, returns a `subscribed` frame |
| Providers | ocr `gemini`, repair `vertex`, prefill `vertex`, storage `gcs` |
| Warm latency | ~0.09 s |

Re-check in one line if you want to be sure before filming:

```bash
curl -s https://medikiosk-api-tjynzes4vq-el.a.run.app/api/v1/hospitals | head -c 120
```

### 2. Cold start is gone — the API now holds one warm instance.

`API_MIN_INSTANCES` defaults to **1**, so there is no cold start to warm away
and `make warm` is no longer a precondition. That costs money continuously,
unlike scale-to-zero; `API_MIN_INSTANCES=0 make deploy` puts it back.

Measured after the change: **0.09 s**, against **8.7 s** cold before it.

### 3. You need a kiosk token to stand in for the device.

`infra/demo/submit_intake.py` reads `KIOSK_TOKEN` from the environment and
never prints it. The deployed token lives in Secret Manager
(`medikiosk-kiosk-tokens`) and on the kiosks themselves:

```bash
export KIOSK_TOKEN='…'          # from your own records, not from this repo
export API=https://medikiosk-api-tjynzes4vq-el.a.run.app
```

If you are driving the real app on a phone instead, you do not need this at all.

### 4. Know what is empty, and do not promise what is not there.

The seeder treats pharmacy stock and service slots as *demo data* and never
re-creates them on a database that already has a hospital row — only
configuration (departments, the facility name) is reconciled. On the existing
cloud database the **Pharmacy and Operations screens will be empty**.

Two honest options:

- **Script around it** (what this script does): show Pharmacy for about eight
  seconds, as proof that roles are separated, and do not present it as an
  inventory product. The chemist's forecasting work is designed and not built.
- Reset the cloud database so the full demo seed runs. Heavier, and your call.

Do **not** claim reorder prediction on camera. It is Phase 5 and it does not
exist yet.

---

## Setup on the desk

Two windows, and decide the layout before you record:

- **Left — the dashboard**, signed in as the doctor, on the Worklist.
- **Right — a terminal**, large font, showing the submission and the GCP
  console or `gcloud` logs.

One rule that will save a take: **do not refresh the dashboard.** The session is
held in memory and nothing is written to `localStorage` — that is a deliberate
decision for a shared OPD terminal, and a refresh signs you out. Use the nav,
never the browser reload button.

Sign in with the **one-click demo buttons** at the bottom of the sign-in card.
Each role lands on its own home screen.

---

## The script

### Beat 1 — what is running, and where (about 40 s)

Start on the terminal, not the UI.

```bash
curl -s $API/readyz | python3 -m json.tool
```

> "Before anything else — this is not a mock. This is the service answering from
> Google Cloud Run in `asia-south1`, Mumbai. Everything in this project is
> region-locked to India by policy, and the deploy scripts refuse to run
> anywhere else — patient data for an Indian hospital stays in India."

Point at the `providers` block as you read it:

> "OCR is Gemini. Repair and prefill are Vertex. Storage is Cloud Storage,
> documents queue through Pub/Sub, the database is Cloud SQL. These are not
> placeholders — they are what this revision is actually configured with, which
> is why they are in the readiness response."

**On screen:** `"environment": "staging"`, the provider list, `"database": "ok"`.

### Beat 2 — the dashboard before anything happens (about 30 s)

Switch to the dashboard, signed in as the doctor.

> "This is the OPD dashboard. Sanjeevani Multi-Specialty Hospital, General
> Medicine. Nobody is waiting — the queue is empty, and the counters agree."

Point at the connection indicator.

> "Top right: **Live**. That is a WebSocket held open to the backend on Cloud
> Run. It is shown on screen on purpose — a dashboard whose connection has
> quietly died looks exactly like a dashboard where nothing is happening, and a
> doctor working down a stale queue is the failure this screen exists to
> prevent."

### Beat 3 — a patient arrives (about 60 s) — **the shot the video is for**

Both windows visible. Terminal on the right.

If you are using the phone: complete an intake in the app and hit submit. If you
are standing in for the kiosk:

```bash
python3 infra/demo/submit_intake.py routine
```

> "This posts exactly what the kiosk and the app post — same endpoint, same
> bearer token, same idempotency key. I am standing in for the device, not
> short-cutting past it."

**Do not touch the dashboard. Let it update itself on camera.**

> "Watch the left-hand side."

The counters go 0 → 1 and the row appears.

> "No refresh. The backend received that record in Mumbai, validated it against
> the contract, ran the red-flag rules, filed it in Cloud SQL, and pushed an
> event down the socket. The dashboard refetched and the patient is in the queue
> — about a second, end to end."

Read the row out:

> "Token, language Hindi, General Medicine, one unresolved field. The patient
> answered in Hindi; the doctor is reading English."

### Beat 4 — the record (about 45 s)

Click **Open Patient File**.

> "This is the structured record, not a transcript."

Point at the Hindi line under an English value:

> "English for the doctor, and the patient's **own words in Hindi underneath**.
> The translation is never the only copy — if the system got it wrong, the
> original is right there to check against."

Scroll to **Past Medical History**.

> "'Not asked.' Not 'no'. This system has five distinct states — answered,
> unresolved, not asked, not applicable, refused — and it will not collapse them.
> A question nobody asked rendered as 'no' is a clinical lie, and it is the
> single most dangerous thing a tool like this could do."

Point at Accept / Amend / Reject.

> "Nothing here is a diagnosis and nothing is signed until a physician verifies
> it. Then it exports as FHIR R4."

### Beat 5 — severity decides the queue (about 60 s)

Back to the Worklist. Two submissions, in this order, pausing between them.

```bash
python3 infra/demo/submit_intake.py high
```

> "A second patient. The device fired a red-flag criterion — prolonged high
> fever. Severity **high**."

It appears **below** the first patient.

> "It flagged, it needs a physician to acknowledge it, and it has **not**
> overtaken anybody. It waits its turn."

```bash
python3 infra/demo/submit_intake.py critical
```

> "Third patient. Breathlessness at rest. Severity **critical** — and the device
> stopped the interview rather than carrying on asking questions."

It lands **at the top**, carrying the chip.

> "Straight to the front, and the list says **why**: 'Moved up — critical flag'.
> A queue that silently reorders itself is a queue nobody trusts."

The point worth landing:

> "Only `critical` jumps. `high` flags, and waits. If every red flag jumped,
> nothing would — and a fever would be overtaking a heart attack."

### Beat 6 — who may see what (about 60 s)

Sign out. **Demo: Receptionist.**

> "Same queue, same hospital, different person."

> "The front desk sees position, token, department, how long each person has
> waited, and that somebody is urgent. It does **not** see one word the patient
> said — and not because the buttons are hidden. The server refuses this role
> the record, the report, the documents and the evidence."

The line worth making explicitly:

> "It is also refused the alerts list, which sounds harmless and is not."

Sign out, **Demo: Doctor**, open **Alerts**, point at `criteria_met`.

> "That is what the alerts list contains: `respiratory.breathlessness = at rest`.
> That is a clinical fact about a named person. The desk needs to know somebody
> is urgent — the queue already says that — not *why*."

Sign out, **Demo: Pharmacy**. Keep this short.

> "The pharmacy counter is a separate role again, with no access to any clinical
> record at all. The shelf is deliberately standalone today; dispensing against a
> named prescription is a later decision with its own privacy argument."

Move on. Do not linger on an empty screen.

### Beat 7 — close (about 30 s)

Back on the doctor's worklist.

> "One loop: a patient answers in their own language on a kiosk or a phone, the
> record goes to Cloud Run in Mumbai, it is validated, screened and stored, and
> it is on a doctor's screen before the patient has sat down — with the queue
> ordered by how sick people are, and every role seeing only what its job needs."

If you want a number:

> "897 tests on the backend, 96 on the dashboard, and a seven-scenario evaluation
> harness that checks the generated report never invents a symptom the patient
> never reported."

---

## If something goes wrong on camera

| Symptom | Cause | Fix |
|---|---|---|
| Queue takes ~10 s to load | the warm instance was scaled away | check `API_MIN_INSTANCES=1` on the revision |
| Connection shows "reconnecting" | websocket not reaching Cloud Run | check the dashboard's proxy target |
| Receptionist/Pharmacy sign-in 401s | you are pointed at an older revision | re-check the API URL |
| Signed out unexpectedly | you refreshed the page | sign in again; never refresh |
| Row does not appear | submission failed | read the terminal — the script prints the intake id |
| Pharmacy/Operations empty | stock is demo data, not re-seeded | expected; keep that beat short |

## What not to say

- Do not call the forecasting feature built. It is designed, not implemented.
- Do not call the sign-in screen a real login — it is a header-auth stand-in and
  says so on screen. If asked: the hospital's identity provider replaces it, and
  header auth is refused in any environment holding real data.
- Do not say the system diagnoses. It records, screens against explicit
  criteria, and routes. Every clinical judgement stays with the physician.

---

## Recording it

### What is on this machine

| Tool | Version | Verdict |
|---|---|---|
| **OBS Studio** | 32.1.2 | **use this** |
| ffmpeg | 6.1.1 | useful for trimming afterwards, not for capture |
| gnome-screenshot | — | stills only |

**This session is Wayland** (`XDG_SESSION_TYPE=wayland`), and that decides it.
ffmpeg's usual `-f x11grab` capture does **not** work on Wayland — it will fail
or record a black rectangle. OBS handles it through PipeWire, which is already
running here (PulseAudio on PipeWire 1.0.5). Nothing to install.

### OBS, first run

1. Skip the auto-configuration wizard, or choose **Optimise for recording**.
2. **Sources → + → Screen Capture (PipeWire)**. A system dialog asks which
   screen or window to share — this is normal on Wayland, and it is asked once
   per source. Pick the whole screen; you will be switching between the browser
   and the terminal, and a single-window capture would lose one of them.
3. **Settings → Output → Recording**:
   - Recording format **mkv** — if OBS or the machine dies mid-take, an mkv is
     still playable, where an mp4 written the same way is not. Remux to mp4 at
     the end (**File → Remux Recordings**).
   - Encoder: hardware (VAAPI/NVENC) if offered, otherwise x264.
   - Quality: **Indistinguishable** or CQP ~20. Text has to stay readable.
4. **Settings → Video**: set Base and Output resolution to the **same** value.
   Scaling is what turns terminal text into mush. 1920×1080 if your display
   allows it.
5. **Settings → Audio**: pick your microphone as Mic/Aux. Mute Desktop Audio —
   there is nothing to capture from the page and it only adds hum.

### Before the take

- **Zoom the browser to 110–125%** (`Ctrl` `+`). What is legible on your screen
  is not legible in a compressed upload.
- **Increase the terminal font size.** The JSON in Beat 1 is the point of that
  shot; if it cannot be read it is just green text.
- Close Slack, mail, and anything that shows a notification banner.
- Hide bookmarks (`Ctrl` `Shift` `B`) — the URL bar is going to be on screen.

### Trimming afterwards

ffmpeg without re-encoding, so nothing is lost and it is instant:

```bash
ffmpeg -i recording.mkv -ss 00:00:04 -to 00:04:30 -c copy demo.mp4
```

To join takes recorded with identical settings:

```bash
printf "file '%s'\n" take1.mkv take2.mkv > list.txt
ffmpeg -f concat -safe 0 -i list.txt -c copy demo.mp4
```

### One habit worth having

Record each beat as its **own take** and join them. A five-minute single take
means one fumbled sentence at 4:40 costs you the whole thing — and the live
submission in Beat 3 is not repeatable without resetting the queue.
