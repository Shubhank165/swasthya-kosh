/**
 * Login → worklist → red-flagged intake → acknowledge → report → evidence →
 * amend → verify. 3/3 §11 item 7, in one pass, against the live backend.
 *
 * The journey is the demo. Every step here is a step somebody will perform in
 * front of a panel, in this order, and the assertions are written for what that
 * person needs to be true rather than for what is convenient to check.
 */
import { expect, test, type Page } from '@playwright/test';

const PHYSICIAN = { id: 'dr-sharma', role: 'physician', hospital: 'aiia-delhi' };

async function signIn(page: Page, who = PHYSICIAN) {
  await page.goto('/');
  await page.getByLabel('User ID').fill(who.id);
  await page.getByLabel('Role').selectOption(who.role);
  await page.getByLabel('Hospital ID').fill(who.hospital);
  await page.getByRole('button', { name: /open the worklist/i }).click();
  await expect(page.getByRole('table')).toBeVisible();
}

test('a physician works one red-flagged intake from the worklist to a verified line', async ({
  page,
}) => {
  await signIn(page);

  // --- the worklist -------------------------------------------------------
  // The alert band is pinned above the list rather than sorted into it: the
  // ordering stays arrival, and urgency is visible without pretending the
  // waiting room was rearranged.
  const band = page.getByTestId('alert-band');
  await expect(band).toBeVisible();
  await expect(band).toContainText(/unacknowledged urgent clinical review/i);

  // The socket is up, and the screen says so. A list that looks live and is not
  // is the failure this indicator exists to prevent.
  await expect(page.getByTestId('connection-state')).toHaveAttribute(
    'data-status',
    'live',
  );

  // --- acknowledge --------------------------------------------------------
  await page.getByRole('link', { name: /open the alerts view/i }).click();
  // Pinned by rule rather than by position. The list is ordered
  // unacknowledged-first, so acknowledging one re-sorts the list and `.first()`
  // is a different card by the time the assertion runs — which is correct
  // behaviour and a broken locator.
  const card = page.locator('[data-alert-id*="gi_bleeding_suspected"]');
  await expect(card).toBeVisible();
  // Never a condition name — the rule's own fixed wording, and the criteria.
  await expect(card).toContainText('Urgent clinical review criterion triggered');
  await expect(card).toContainText('haematemesis');

  // Two controls, and they are not the same control.
  await expect(card.getByTestId('acknowledge')).toBeVisible();
  await expect(card.getByTestId('escalate')).toBeVisible();
  await card.getByTestId('acknowledge').click();
  await expect(card).toHaveAttribute('data-acknowledged', 'true');
  await expect(card).toContainText('dr-sharma');

  // --- the report ---------------------------------------------------------
  // Straight from the alert to the intake it fired on, which is what the
  // physician actually does next.
  await card.getByRole('link').first().click();

  await expect(page.getByText(/draft report — requires physician verification/i)).toBeVisible();
  // Coverage as a count, not a percentage.
  await expect(page.getByTestId('coverage')).toContainText(/\d+ of \d+ answered/);
  // Unresolved is a full section, never a disclosure.
  const unresolved = page.getByTestId('unresolved-section');
  await expect(unresolved).toBeVisible();
  await expect(unresolved.locator('details')).toHaveCount(0);

  // --- evidence -----------------------------------------------------------
  // One click from a line to what it rests on. This is the demo moment.
  const line = page.locator('[data-fact-id]').first();
  await line.click();
  await expect(page.getByLabel('Evidence')).toBeVisible();

  // --- amend --------------------------------------------------------------
  // The duration line. Its value is a `Duration` in the record, so the inline
  // editor offers a magnitude and a unit rather than a text box — a correction
  // the report can still compare with itself afterwards.
  const durationRow = page.locator('li', { hasText: '3 days' }).first();
  await durationRow.hover();
  await durationRow.getByTestId('amend').click();
  const editor = page.getByTestId('amend-editor');
  await editor.getByLabel('Corrected value').fill('5');
  await editor.getByLabel('Reason').fill('patient corrected on arrival');
  await editor.getByTestId('amend-save').click();
  // The line comes back from the server as a new revision, marked as corrected
  // by a physician rather than merely confirmed.
  await expect(page.getByText('corrected by physician').first()).toBeVisible();

  // --- verify -------------------------------------------------------------
  await page.getByTestId('verify-all').click();
  await expect(page.getByText(/verified by dr-sharma/i)).toBeVisible();
});

test('staff may read the record and may not verify it', async ({ page }) => {
  await signIn(page, { id: 'nurse-2', role: 'staff', hospital: 'aiia-delhi' });
  await page.getByTestId('worklist-row').first().click();

  await expect(page.getByText(/draft report/i)).toBeVisible();
  // Verification is the one act that changes the clinical weight of the record.
  await expect(page.getByTestId('verify-all')).toHaveCount(0);
  await expect(page.getByTestId('accept')).toHaveCount(0);
});

test('reloading the page clears the session rather than restoring it', async ({
  page,
}) => {
  // §8, and §12's "do not store tokens in localStorage" seen from the outside.
  // A dashboard left open on a shared OPD terminal must not survive a reload —
  // and this is what proves nothing was persisted, whatever the code says.
  await signIn(page);
  await page.reload();
  await expect(page.getByRole('button', { name: /open the worklist/i })).toBeVisible();
  await expect(page.getByRole('table')).toHaveCount(0);

  const stored = await page.evaluate(() => ({
    local: { ...window.localStorage },
    session: { ...window.sessionStorage },
  }));
  expect(stored.local).toEqual({});
  expect(stored.session).toEqual({});
});

test('the quality view is admin-only and refuses without showing half of it', async ({
  page,
}) => {
  await signIn(page);
  // Navigated through the router rather than by URL: a fresh page load clears
  // the in-memory session by design, and the assertion here is about the role
  // gate rather than about that.
  await page.evaluate(() => window.history.pushState({}, '', '/metrics'));
  await page.evaluate(() => window.dispatchEvent(new PopStateEvent('popstate')));
  await expect(page.getByTestId('refusal')).toBeVisible();
  await expect(page.getByText(/correction rate/i)).toHaveCount(0);
});

test('the whole report is reachable from the keyboard', async ({ page }) => {
  await signIn(page);
  await page.getByTestId('worklist-row').first().click();
  await expect(page.getByText(/draft report/i)).toBeVisible();

  // Tab until a report line has focus, then open its evidence with Enter. A
  // physician with a patient in front of them is not reaching for a trackpad.
  let landed = false;
  for (let index = 0; index < 60 && !landed; index += 1) {
    await page.keyboard.press('Tab');
    landed = await page.evaluate(
      () => document.activeElement?.hasAttribute('data-fact-id') ?? false,
    );
  }
  expect(landed).toBe(true);
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Evidence')).toBeVisible();
});

test('no clinical text reaches the browser console', async ({ page }) => {
  // §11 item 9. Every extension the physician has installed can read it.
  const written: string[] = [];
  page.on('console', (message) => written.push(message.text()));

  await signIn(page);
  await page.getByTestId('worklist-row').first().click();
  await page.locator('[data-fact-id]').first().click();
  await expect(page.getByLabel('Evidence')).toBeVisible();

  const log = written.join('\n');
  // The fixture intake is a Hindi interview; any Devanagari in the console is
  // a patient's own words in a place they must never be.
  expect(log).not.toMatch(/[ऀ-ॿ]/);
  expect(log.toLowerCase()).not.toContain('metformin');
});
