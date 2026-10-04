# Record this

**Setup:** one browser window, two tabs. A terminal sitting behind it that you
visit for three seconds at a time.

- **Tab 1** — the dashboard
- **Tab 2** — Google Cloud logs

Switch tabs with **Ctrl Tab**. Get to the terminal with **Alt Tab**.

---

# PART 1 — OBS, first time

### Open it

```bash
obs
```

### The wizard (appears on first launch)

1. **Optimize just for recording, I will not be streaming** → **Next**
2. Base Resolution **1920×1200**, FPS **30** → **Next**
3. **Apply Settings**

### Add your screen

1. **Sources** panel (bottom left) → click **+**
2. Choose **Screen Capture (PipeWire)** → name it `Screen` → **OK**
3. A dialog asks you to share your screen → pick your monitor → **Share**
4. **OK**

You should see your screen in the preview. If it's black, right-click the
source → **Properties** → share again.

### Settings (click **Settings**, bottom right)

**Video**
- Base Resolution: **1920×1200**
- Output Resolution: **1920×1200** ← same as Base, or your text goes blurry
- FPS: **30**

**Output**
- Output Mode: **Simple**
- Recording Quality: **High Quality, Medium File Size**
- Recording Format: **MKV**
- Encoder: **Hardware** if offered, else **Software (x264)**

**Audio**
- Mic/Auxiliary: your microphone
- Desktop Audio: **Disabled**

**OK**.

### Test your mic

Say something. The **Mic/Aux** bar in the Audio Mixer should move, green to
yellow, never red.

### Recording

**Start Recording** / **Stop Recording**, bottom right. Files go to `~/Videos`.

### When you're done

**File → Remux Recordings** → add your MKV → **Remux**. That gives you an MP4.

Trim the dead air:

```bash
cd ~/Videos
ffmpeg -i YOUR_FILE.mp4 -ss 00:00:03 -to 00:04:00 -c copy final.mp4
```

---

# PART 2 — Set up before you record

### Terminal — start the dashboard

```bash
cd ~/SIH2/medikiosk/dashboard
MEDIKIOSK_API=https://medikiosk-api-tjynzes4vq-el.a.run.app npm run dev
```

Leave that running. Open a **second** terminal tab:

```bash
cd ~/SIH2/medikiosk
export API=https://medikiosk-api-tjynzes4vq-el.a.run.app
export KIOSK_TOKEN='<your token>'
```

Make the font big — **Ctrl `+`** a few times. This is the terminal you'll
Alt-Tab to.

### Browser — one window, two tabs

**Tab 1:** `http://localhost:5173`
- Zoom in once: **Ctrl `+`**
- Hide bookmarks: **Ctrl Shift B**
- Click **Demo: Doctor**

**Tab 2:**
`https://console.cloud.google.com/run/detail/asia-south1/medikiosk-api/logs?project=medikiosk-sih-2026`
- **Sign in to Google now.** Dismiss any welcome banners now, not on camera.

Leave the browser on **Tab 1**.

### Last checks

- Close Slack, WhatsApp, mail
- Turn on **Do Not Disturb**
- **Never press reload.** It signs you out.

---

# PART 3 — The script

Record each beat separately, then join them.

---

## BEAT 1 — What the doctor walks in to  (~40 sec)

**SHOW:** Tab 1, the queue.

**SAY:**

> "This is what a doctor sees when they sit down at the OPD counter. Sanjeevani
> Hospital, General Medicine."

**DO:** Move the cursor across the four counters at the top.

**SAY:**

> "How many people are waiting, how many are ready to be seen, how many are
> still answering questions at the kiosk, and whether anything urgent has come
> up. Three patients have already been through this morning — you can see them
> marked Seen. Nobody's waiting right now."

**DO:** Point at the green **Live** dot.

**SAY:**

> "And it says Live — the screen keeps itself up to date. The doctor never has
> to refresh anything."

---

## BEAT 2 — A patient arrives  (~50 sec)

**DO:** **Alt Tab** to the terminal.

**SAY:**

> "Let's say a patient finishes their intake out at the kiosk."

**DO:**
```bash
python3 infra/demo/submit_intake.py routine
```

**DO:** **Alt Tab** straight back to the browser. Then stop touching anything.

**SAY:**

> "Watch the queue."

**DO:** Wait for the row to appear.

**SAY:**

> "There they are. Nobody refreshed anything — the patient walked up to a kiosk,
> answered questions in Hindi, and by the time they sit down the doctor already
> has their case."

**DO:** Point at the row.

**SAY:**

> "Token number, what they came in for, which department, and a note that one
> answer still needs sorting out."

---

## BEAT 3 — Quick look behind the scenes  (~25 sec)

**DO:** **Ctrl Tab** to Tab 2.

**SAY:**

> "Quick look at the back end while we're here — this is running on Google
> Cloud, in the Mumbai region."

**DO:** Point at the most recent log line.

**SAY:**

> "That's the submission that just came in, a few seconds ago."

**SAY:**

> "And you'll notice there's nothing personal in these logs — no symptoms, no
> names, no phone numbers. Just reference numbers. That's deliberate."

**DO:** **Ctrl Tab** back to Tab 1.

---

## BEAT 4 — The patient's record  (~70 sec)

**DO:** Click **Open Patient File**.

**SAY:**

> "This is the part that saves the doctor time. Instead of a recording or a wall
> of text, the patient's answers come through already sorted into a proper case
> sheet."

**DO:** Point at a Hindi line under an English value.

**SAY:**

> "The doctor reads it in English. Underneath, in smaller text, is exactly what
> the patient said in Hindi. So if anything looks off, the original is right
> there to check — we never throw away their own words."

**DO:** Scroll to **Past Medical History**.

**SAY:**

> "And look at this one. It says 'Not asked.' Not 'no'. That's an important
> difference — if nobody asked a patient about their heart history, the doctor
> needs to know that it's an open question, not a clean record."

**DO:** Point at **Accept / Amend / Reject**.

**SAY:**

> "Nothing here is a diagnosis, and nothing is final. The doctor goes through it
> and accepts, corrects, or throws out each line. It's a head start, not a
> decision."

**DO:** Point at **Verify Intake & Export FHIR R4**.

**SAY:**

> "Once they sign off, it exports in the standard format hospital systems use,
> so it can go straight into the hospital's records."

---

## BEAT 5 — The urgent ones come first  (~50 sec)

**DO:** Click **Back to OPD queue**. Then **Alt Tab** to the terminal.

**DO:**
```bash
python3 infra/demo/submit_intake.py high
```

**DO:** **Alt Tab** back.

**SAY:**

> "Second patient. This one's running a high fever, and the kiosk flagged it."

**DO:** Wait. It appears **below** the first patient.

**SAY:**

> "It's marked for the doctor's attention — but it hasn't jumped the queue. It
> waits its turn, like it should."

**DO:** **Alt Tab**, run, **Alt Tab** back:
```bash
python3 infra/demo/submit_intake.py critical
```

**SAY:**

> "Now this one. Breathless just sitting still. The kiosk stopped asking
> questions and flagged it immediately."

**DO:** Wait. It lands at the **top**.

**SAY:**

> "Straight to the front of the queue — and it tells the doctor why, right
> there: moved up, critical flag."

**SAY:**

> "That's the bit we spent the most time on. Only the genuinely serious cases
> jump. If every flag jumped the queue, none of them would mean anything — and
> a fever would be pushing ahead of a heart attack."

---

## BEAT 6 — Not everyone sees everything  (~35 sec)

**DO:** Click the **sign-out icon** (top right) → **Demo: Receptionist**.

**SAY:**

> "Same hospital, but this is the front desk."

**DO:** Point at the table.

**SAY:**

> "They get what they need to run the waiting room — who's next, how long
> they've been waiting, whether someone needs to be pushed ahead. But not a word
> about what's actually wrong with anyone. That stays between the patient and
> the doctor."

---

## BEAT 7 — Close  (~20 sec)

**DO:** Sign out → **Demo: Doctor**.

**SAY:**

> "So that's it. A patient answers questions in their own language at a kiosk.
> By the time they sit down, the doctor has a proper case sheet, the urgent
> cases are already at the top, and everyone in the hospital sees exactly as
> much as their job needs."

**DO:** Stop recording.

---

# Don't say

- Don't claim the pharmacy predicts stock orders — that part isn't built yet.
- Don't call the login screen real. It's a placeholder until the hospital's own
  system is connected.
- Don't say it diagnoses anything. It takes the history and flags the urgent
  ones.

# If something breaks

| Problem | Fix |
|---|---|
| Row doesn't show up | Check the terminal — it prints an error or the ID |
| Says "reconnecting" | The first terminal stopped. Restart it |
| You got signed out | You hit reload. Just sign in again |
| OBS preview is black | Right-click the source → Properties → share again |
| Cloud logs look frozen | Click **Stream logs** at the top of the panel |
