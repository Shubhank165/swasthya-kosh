# MediKiosk dashboard — 3/3

The screen a physician looks at while a patient walks in. React 18 + TypeScript
+ Vite; the backend from 1/3 already exposes almost everything it needs, so this
is nearly all client.

```
npm install
npm run api:types        # regenerate the typed client from the backend's OpenAPI
npm run dev              # proxies /api and /ws to MEDIKIOSK_API (default :8000)
npm test                 # vitest
npm run typecheck        # tsc --noEmit
npm run lint
npm run e2e              # Playwright, against a real backend it starts itself
```

`npm run e2e` needs no running server. `playwright.config.ts` starts
`backend/scripts/e2e_backend.py`, which boots the **real application** on a
throwaway SQLite file and seeds two intakes, one of which fired a red-flag
criterion on the device. A journey run against a hand-written stub proves that
the stub matches the test's idea of the API, which is not the thing worth
knowing.

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
  original script, with a translation beneath. The doctor's interface switches
  between English and Hindi; the record does not switch with it.
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
| `src/lib/realtime.ts` | The worklist socket. On reconnect it **refetches rather than replays**, and it says out loud when it is not connected. |
| `src/report/VerifyControls.tsx` | Accept, amend, reject — three acts, and rejecting is never a "no". |
| `src/evidence/fromApi.ts` | Where the backend's `FactChannel` vocabulary becomes what the physician is about to look at. |
| `.eslintrc.cjs` | Two of the rules are project rules: no `localStorage`, no `console`. |
| `src/i18n/strings.ts` | English and Hindi. **Chrome only** — the record is never translated; see the note at the top of the file. |


## Sign-in is a stand-in, and says so on screen

There is no dashboard login endpoint, because there is no identity provider
integration yet. The sign-in form sets the backend's **header principal**
(`X-User-Id` / `X-User-Role` / `X-Hospital-Id`), which `app/api/auth.py` gates on
`ALLOW_HEADER_AUTH` and which is off in any environment holding real data.

The screen states this in a box under the form. A demo that quietly looked like
a real login would be claiming an integration this project does not have.
Replacing it changes `setAccessToken`, `LoginPage` and nothing else.

## What is deliberately absent

- **Queue management.** No calling, recalling, deferring, transferring or token
  issuing. §4.1: the spec does not ask for it, `stale/queue/`
  already holds a version of it, and it is surface area to defend with no marks
  attached. A list the doctor works down is enough.
- **Any client-side clinical derivation.** Coverage is arithmetic over facts the
  backend sent; everything else arrives decided.
- **A resolution for a conflict.** Both claims, both sources, no winner — the
  backend does not pick one either.
