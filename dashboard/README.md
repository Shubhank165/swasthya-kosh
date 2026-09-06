# MediKiosk dashboard — 3/3

The screen a physician looks at while a patient walks in. React 18 + TypeScript
+ Vite; the backend from 1/3 already exposes almost everything it needs, so this
is nearly all client.

```
npm install
npm run api:types        # regenerate the typed client from the backend's OpenAPI
npm run dev              # proxies /api and /ws to MEDIKIOSK_API (default :8000)
npm test
npm run typecheck
```

## What this build will not do

- **It never computes clinical content.** Coverage, red flags, contradictions
  and every rendered line arrive from the backend already decided. The moment a
  component starts deriving one, the dashboard has a clinical opinion and two
  systems disagree about the same patient.
- **It never merges acknowledge and escalate.** Two actions, two controls, both
  recorded with the acting user.
- **It never hides unresolved or conflicting facts** behind a toggle. Those are
  full sections. The honesty of this system is the product.
- **It never translates the patient's own words in place.** Verbatim, in the
  original script, with a translation beneath.
- **It never puts a token in localStorage**, and never a clinical string in the
  console.

## Where the interesting parts are

| Path | What it is |
|---|---|
| `src/report/factState.ts` | **The file that makes or breaks the screen.** How a fact's state becomes a label, a glyph and a chip. Pure, and tested hardest. |
| `src/report/ReportView.tsx` | Sections in the fixed order, then Unresolved and Conflicts as full sections. |
| `src/evidence/EvidencePanel.tsx` | The demo moment: one click from a line to the transcript turn, the boxed document region, or the tapped option. |
| `src/api/client.ts` | Access token in memory only; errors carry status, method and path and never a body. |
| `src/auth/session.ts` | The four roles that may see this screen. `patient` and `kiosk` are refused outright. |
