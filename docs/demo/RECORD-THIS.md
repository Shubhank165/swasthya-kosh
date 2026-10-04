# Record this

Two parts: **set up OBS once**, then **follow the shot list**.
Left column = what you do. Right of it = what you say, word for word.

---

# PART 1 — OBS, first time

You have OBS 32.1.2 installed. You are on Ubuntu GNOME with Wayland at
1920×1200. These steps are for exactly that.

### 1. Open it

```bash
obs
```

A wizard appears on first launch.

### 2. Auto-Configuration Wizard

1. Select **Optimize just for recording, I will not be streaming**
2. **Next**
3. Base Resolution: pick **1920×1200**. FPS: **30**
4. **Next** → it runs a test → **Apply Settings**

### 3. Add the screen capture

1. Bottom-left panel called **Sources** → click **+**
2. Choose **Screen Capture (PipeWire)**
3. Name it `Screen` → **OK**
4. A GNOME dialog opens: **"Share your screen"** → pick your monitor → click
   **Share**
5. **OK**

You should now see your own screen in the OBS preview.

> If the preview is black: you clicked Cancel on the share dialog. Right-click
> the source → **Properties** → **Select Screen** → share again.

### 4. Settings that decide if your video is readable

Click **Settings** (bottom right).

**Video:**
- Base (Canvas) Resolution: **1920×1200**
- Output (Scaled) Resolution: **1920×1200** ← must be identical to Base
- FPS: **30**

**Output:**
- Output Mode: **Simple**
- Recording Quality: **High Quality, Medium File Size**
- Recording Format: **MKV**
- Encoder: **Hardware** if listed, otherwise **Software (x264)**

**Audio:**
- Mic/Auxiliary Audio: your microphone
- Desktop Audio: **Disabled**

Click **OK**.

### 5. Check your mic

Look at the **Audio Mixer** panel. Say something. The **Mic/Aux** bar must move
and stay in the green/yellow — not touching red.

If the bar does not move: click the gear next to Mic/Aux → **Properties** →
pick the right device.

### 6. Recording

- Start: **Start Recording** (bottom right)
- Stop: **Stop Recording**
- Files land in `~/Videos`

### 7. After you finish

Convert MKV to MP4 — **File → Remux Recordings** → add your file → **Remux**.

To cut the dead air at the start and end:

```bash
cd ~/Videos
ffmpeg -i YOUR_FILE.mp4 -ss 00:00:03 -to 00:04:30 -c copy final.mp4
```

---

# PART 2 — Set up the desk

### Terminal 1 — start the dashboard pointed at Google Cloud

```bash
cd ~/SIH2/medikiosk/dashboard
MEDIKIOSK_API=https://medikiosk-api-tjynzes4vq-el.a.run.app npm run dev
```

Leave it running. Do not record this terminal.

### Terminal 2 — the one you WILL record

```bash
cd ~/SIH2/medikiosk
export API=https://medikiosk-api-tjynzes4vq-el.a.run.app
export KIOSK_TOKEN='<your kiosk token>'
```

Then make the font big: **Ctrl `+`** about four times.

### Browser — open these four tabs, in this order

| Tab | URL |
|---|---|
| 1. Dashboard | `http://localhost:5173` |
| 2. Cloud Run | `https://console.cloud.google.com/run/detail/asia-south1/medikiosk-api/metrics?project=medikiosk-sih-2026` |
| 3. Cloud Run logs | `https://console.cloud.google.com/run/detail/asia-south1/medikiosk-api/logs?project=medikiosk-sih-2026` |
| 4. Cloud SQL | `https://console.cloud.google.com/sql/instances/medikiosk-pg/overview?project=medikiosk-sih-2026` |

**Sign in to Google in tabs 2–4 now**, before you record. Dismiss any
"Welcome to Cloud Console" banners now too.

Then on tab 1:

1. Zoom to **110%**: **Ctrl `+`** once
2. Hide bookmarks: **Ctrl Shift B**
3. Click **Demo: Doctor**

### Final checks

- Close Slack, WhatsApp, mail
- Notifications off: top-right menu → **Do Not Disturb**
- **Never press F5 or reload.** It signs you out.

---

# PART 3 — The shot list

Record each beat separately. Stop recording between beats.

---

## BEAT 1 — Where this runs  (~50 sec)

**SHOW:** Browser tab 2 — the Cloud Run service page in the Google Cloud
Console.

**SAY:**

> "This is the Google Cloud Console. Project MediKiosk. This is our API running
> on Cloud Run."

**DO:** Point at the **Region** field.

**SAY:**

> "Region: asia-south1 — Mumbai. Everything in this project is region-locked to
> India. The deploy scripts refuse to run anywhere else, so patient data cannot
> leave the country by accident."

**DO:** Point at the service **URL**, then click the **Revisions** tab.

**SAY:**

> "Live revision, serving 100% of traffic. Minimum instances is one, so there's
> no cold start — the service is always up."

**DO:** Switch to browser tab 4 — **Cloud SQL**.

**SAY:**

> "The database is Cloud SQL — Postgres 16, also in Mumbai, on a private IP.
> It's not reachable from the internet; only our Cloud Run services can see it."

**DO:** Switch back to tab 2.

**SAY (optional, if you want the full stack named):**

> "Documents go to Cloud Storage, OCR is queued through Pub/Sub, and the models
> are Gemini and Vertex AI — all in the same region."

---

## BEAT 2 — The dashboard, before  (~30 sec)

**SHOW:** Browser, doctor's Worklist.

**SAY:**

> "This is the OPD dashboard. Sanjeevani Multi-Specialty Hospital, General
> Medicine counter. One patient already consulted this morning, marked Seen.
> Nobody waiting — all four counters are at zero."

**DO:** Point at the green **Live** dot, top right of the hospital card.

**SAY:**

> "Top right it says Live. That's an open WebSocket to Cloud Run. We show the
> connection state on screen on purpose — a dashboard that has silently
> disconnected looks exactly like a quiet waiting room."

---

## BEAT 3 — A patient arrives  ⭐ THE MAIN SHOT  (~60 sec)

**SHOW:** Split screen — browser on the left, Terminal 2 on the right. Both
visible at the same time.

**SAY:**

> "Now a patient finishes their intake on the kiosk."

**DO:**
```bash
python3 infra/demo/submit_intake.py routine
```

**SAY:**

> "That posts exactly what the kiosk and the phone app post — same endpoint,
> same token. I'm standing in for the device, not skipping it."

**DO:** **Nothing.** Hands off the keyboard. Let the dashboard update itself.

**SAY:**

> "Watch the left side. No refresh."

**DO:** Wait for the row to appear and the counters to change.

**SAY:**

> "That record went to Mumbai, got validated against the contract, screened for
> red flags, written to Cloud SQL, and pushed back down the socket. One second,
> end to end. The patient is in the queue before they've sat down."

**DO:** Point at the row.

**SAY:**

> "Token number, language Hindi, General Medicine, one unresolved field."

**SAY (lead into the next shot):**

> "You've only got my word so far that this went to the cloud. Let me show you."

---

## BEAT 3B — Proof it hit Google  ⭐ (~45 sec)

**SHOW:** Browser tab 3 — **Cloud Run → Logs**.

**DO:** Make sure the log stream is scrolled to the newest entry. If it isn't
updating, click the **Play / Stream logs** button at the top of the log panel.

**SAY:**

> "That submission didn't go to my laptop. Here are Google's own logs for the
> service, live."

**DO:** Point at the line reading `POST .../api/v1/intakes/ingest` with status
`200`.

**SAY:**

> "There it is. POST to the ingest endpoint, status 200, ninety milliseconds —
> the request I just made, logged by Cloud Run."

**DO:** Point at the `intake_ingested` line just below it.

**SAY:**

> "And our own structured log underneath: intake_ingested, with the intake ID.
> Match it against the token on the dashboard — same record."

**SAY (this one is worth landing):**

> "Notice what's *not* here. No symptoms, no names, no phone numbers. These logs
> carry identifiers and counters only. That isn't a convention we follow — we
> have a test that writes clinical text into a log call and fails the build if
> any of it comes out the other side."

---

## BEAT 4 — The record  (~45 sec)

**DO:** Click **Open Patient File**.

**SAY:**

> "This is a structured record, not a transcript."

**DO:** Point at the Hindi text under an English value.

**SAY:**

> "English for the doctor, and the patient's own Hindi words underneath. The
> translation is never the only copy — if we got it wrong, the original is right
> there."

**DO:** Scroll to **Past Medical History**.

**SAY:**

> "Look at this: 'Not asked.' Not 'no'. We keep five separate states — answered,
> unresolved, not asked, not applicable, refused — and we never collapse them. A
> question nobody asked, shown as 'no', is a clinical lie."

**DO:** Point at the Accept / Amend / Reject buttons.

**SAY:**

> "Nothing is diagnosed and nothing is signed until the doctor verifies it. Then
> it exports as FHIR R4."

---

## BEAT 5 — Severity decides the queue  (~60 sec)

**DO:** Click **Back to OPD queue**.

**DO:**
```bash
python3 infra/demo/submit_intake.py high
```

**SAY:**

> "Second patient. The device fired a red flag — prolonged high fever. Severity:
> high."

**DO:** Wait. It appears **below** the first patient.

**SAY:**

> "It's flagged, a doctor has to acknowledge it — but it has not jumped the
> queue. It waits its turn."

**DO:**
```bash
python3 infra/demo/submit_intake.py critical
```

**SAY:**

> "Third patient. Breathlessness at rest. Severity: critical — and the device
> stopped asking questions rather than carrying on."

**DO:** Wait. It lands at the **top**.

**SAY:**

> "Straight to the front. And the list says why — 'Moved up, critical flag'. A
> queue that silently reorders itself is a queue nobody trusts."

**SAY (land this one):**

> "Only critical jumps. High flags, and waits. If every red flag jumped the
> queue, none of them would — and a fever would be overtaking a heart attack."

---

## BEAT 6 — Who sees what  (~60 sec)

**DO:** Click the **sign-out icon** (top right) → click **Demo: Receptionist**.

**SAY:**

> "Same hospital, same queue, different person."

**DO:** Point at the table.

**SAY:**

> "The front desk sees position, token, department, waiting time, and that
> someone is urgent. It does not see a single word the patient said. And that's
> not hidden buttons — the server refuses this role the record, the report, the
> documents and the alerts."

**DO:** Sign out → **Demo: Doctor** → click the **Alerts** tab.

**DO:** Point at the `Criteria met` line.

**SAY:**

> "This is why the front desk doesn't get the alerts page. 'Breathlessness at
> rest' is a clinical fact about a named person. The desk needs to know someone
> is urgent — the queue already tells them that. Not why."

**DO:** Sign out → **Demo: Pharmacy**. Stay about 8 seconds.

**SAY:**

> "And the pharmacy counter is a third role, with no access to any clinical
> record at all."

**DO:** Move on.

---

## BEAT 7 — Close  (~30 sec)

**DO:** Sign out → **Demo: Doctor**. Back on the queue.

**SAY:**

> "So that's the loop. A patient answers in their own language on a kiosk or a
> phone. It goes to Google Cloud in Mumbai, gets validated, screened and stored.
> It's on the doctor's screen in about a second — ordered by how sick people
> are, with every role seeing only what their job needs."

**SAY:**

> "897 tests on the backend, 97 on the dashboard, and an evaluation harness that
> checks the generated report never invents a symptom the patient never
> reported."

**DO:** Stop recording.

---

# Do not say

- Do **not** say the pharmacy predicts reorder quantities. Not built yet.
- Do **not** call the sign-in screen a real login. It's a stand-in until the
  hospital's identity provider is wired in.
- Do **not** say the system diagnoses. It records, screens, and routes.

# If it breaks

| Problem | Fix |
|---|---|
| Row doesn't appear | Check Terminal 2 — the script prints the intake id or an error |
| Says "reconnecting" | Terminal 1 died. Restart it |
| Got signed out | You pressed reload. Sign in again |
| Blank/black OBS preview | Right-click source → Properties → share the screen again |
| Console logs not moving | Click **Stream logs** at the top of the log panel |
| Logs show nothing recent | Set the time range to **Last 1 hour** and clear any query filter |
| Console asks you to log in mid-take | You skipped the sign-in step in Part 2. Stop, sign in, re-record |

## Backup if the Console is slow or won't cooperate

Run this in Terminal 2 instead of Beat 3B — same proof, no browser:

```bash
gcloud logging read \
  'resource.labels.service_name="medikiosk-api" AND httpRequest.requestMethod="POST"' \
  --project=medikiosk-sih-2026 --limit=3 \
  --format='value(timestamp,httpRequest.requestUrl,httpRequest.status)'
```

It prints the same request Cloud Run logged, straight from Google.
