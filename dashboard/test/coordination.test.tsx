/**
 * What the coordination screens are allowed to say.
 *
 * The tests worth having here are the ones that pin distinctions a redesign
 * could flatten without anyone noticing: an unfilled referral is not a pending
 * one, an unconfident wait estimate is not a number, and a medicine nobody
 * recorded is not a medicine that has run out. All three are cheap to collapse
 * in a component and expensive to discover on a ward.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { OperationsPage } from '../src/coordination/OperationsPage';
import { OrdersPanel } from '../src/coordination/OrdersPanel';
import { renderWithProviders, signInAs, signOut, stubFetch } from './harness';

const INTAKE = '3f1c2a10-0000-4000-8000-000000000001';

afterEach(() => {
  signOut();
  vi.unstubAllGlobals();
});

const ORDERS = {
  intake_id: INTAKE,
  orders: [
    {
      id: 'ord_1',
      intake_id: INTAKE,
      kind: 'imaging',
      code: 'usg_abdomen',
      display: 'Ultrasound, abdomen',
      status: 'scheduled',
      destination: 'radiology',
      slot_at: '2026-09-29T09:00:00Z',
      ordered_by: 'dr-a',
      created_at: '2026-09-28T09:00:00Z',
    },
    {
      id: 'ord_2',
      intake_id: INTAKE,
      kind: 'referral',
      code: 'physio_opd',
      display: 'Physiotherapy OPD',
      status: 'unfilled',
      destination: 'physiotherapy',
      slot_at: null,
      ordered_by: 'dr-a',
      created_at: '2026-09-28T09:01:00Z',
    },
  ],
};

function ordersRoutes(wait: Record<string, unknown>) {
  return {
    [`GET /intakes/${INTAKE}/orders`]: () => ({ body: ORDERS }),
    [`GET /intakes/${INTAKE}/wait`]: () => ({ body: wait }),
  };
}

const CONFIDENT = {
  intake_id: INTAKE,
  position: 3,
  ahead: 2,
  minutes: 14,
  confident: true,
};

const UNSURE = {
  intake_id: INTAKE,
  position: 3,
  ahead: 2,
  minutes: null,
  confident: false,
};

describe('the orders panel', () => {
  it('shows a booked slot as a time and an unfilled referral as neither', async () => {
    signInAs('physician');
    stubFetch(ordersRoutes(CONFIDENT));
    renderWithProviders(<OrdersPanel intakeId={INTAKE} />);

    const list = await screen.findByTestId('orders-list');
    const scheduled = within(list).getByText('Ultrasound, abdomen').closest('li');
    const unfilled = within(list).getByText('Physiotherapy OPD').closest('li');

    expect(scheduled?.textContent).toMatch(/29 Sep|Sep 29/i);
    // The status words are different because the states are different, and a
    // referral that found no capacity must never read as one still waiting.
    expect(within(unfilled as HTMLElement).getByText(/no capacity offered/i)).toBeTruthy();
    expect(within(unfilled as HTMLElement).getByText(/no slot available/i)).toBeTruthy();
  });

  it('gives a time only when the backend says it can stand behind one', async () => {
    signInAs('physician');
    stubFetch(ordersRoutes(CONFIDENT));
    renderWithProviders(<OrdersPanel intakeId={INTAKE} />);

    const estimate = await screen.findByTestId('wait-estimate');
    expect(estimate.textContent).toMatch(/Position 3/);
    expect(estimate.textContent).toMatch(/about 14 min/);
  });

  it('shows a position and no number when it is not confident', async () => {
    signInAs('physician');
    stubFetch(ordersRoutes(UNSURE));
    renderWithProviders(<OrdersPanel intakeId={INTAKE} />);

    const estimate = await screen.findByTestId('wait-estimate');
    expect(estimate.textContent).toMatch(/Position 3/);
    // Not rounded up into "a few minutes". A waiting room given a number that
    // turns out wrong stops believing the screen.
    expect(estimate.textContent).not.toMatch(/\d+ min/);
    expect(estimate.textContent).toMatch(/too few consultations/i);
  });

  it('offers the issue form to a physician and not to other clinical staff', async () => {
    signInAs('staff');
    stubFetch(ordersRoutes(CONFIDENT));
    const { unmount } = renderWithProviders(<OrdersPanel intakeId={INTAKE} />);
    await screen.findByTestId('orders-list');
    expect(screen.queryByTestId('issue-order')).toBeNull();
    unmount();

    signInAs('physician');
    renderWithProviders(<OrdersPanel intakeId={INTAKE} />);
    expect(await screen.findByTestId('issue-order')).toBeTruthy();
  });

  it('sends the order the form describes and nothing it does not', async () => {
    signInAs('physician');
    const { calls } = stubFetch({
      ...ordersRoutes(CONFIDENT),
      [`POST /intakes/${INTAKE}/orders`]: () => ({
        status: 201,
        body: { ...ORDERS.orders[0], id: 'ord_3' },
      }),
    });
    renderWithProviders(<OrdersPanel intakeId={INTAKE} />);
    await screen.findByTestId('issue-order');

    await userEvent.type(screen.getByLabelText('Code'), 'cbc');
    await userEvent.type(screen.getByLabelText('Description'), 'Complete blood count');
    await userEvent.click(screen.getByTestId('issue-order-submit'));

    await waitFor(() => {
      const posted = calls.find((call) => call.method === 'POST');
      expect(posted?.body).toEqual({
        kind: 'lab',
        code: 'cbc',
        display: 'Complete blood count',
      });
    });
  });

  it('will not issue an order with no label behind the code', async () => {
    signInAs('physician');
    stubFetch(ordersRoutes(CONFIDENT));
    renderWithProviders(<OrdersPanel intakeId={INTAKE} />);
    await screen.findByTestId('issue-order');

    await userEvent.type(screen.getByLabelText('Code'), 'cbc');
    // A code nobody can read is not a handover.
    expect(screen.getByTestId('issue-order-submit')).toBeDisabled();
  });
});

const OPERATIONS = {
  generated_at: '2026-09-28T10:00:00Z',
  departments: [
    {
      department_code: 'kayachikitsa',
      waiting: 2,
      flagged: 0,
      longest_wait_minutes: 90,
      unfilled_orders: 0,
    },
    {
      department_code: 'general',
      waiting: 5,
      flagged: 1,
      longest_wait_minutes: 30,
      unfilled_orders: 2,
    },
  ],
};

const STOCK = {
  generated_at: '2026-09-28T10:00:00Z',
  alerts: [
    {
      code: 'ors_sachet',
      display: 'ORS sachet',
      on_hand: 90,
      reorder_level: 50,
      expires_on: '2026-09-25',
      state: 'expired',
    },
    {
      code: 'pantoprazole_40',
      display: 'Pantoprazole 40 mg',
      on_hand: 0,
      reorder_level: 40,
      expires_on: null,
      state: 'out',
    },
  ],
};

describe('the operations view', () => {
  function stub() {
    return stubFetch({
      'GET /operations': () => ({ body: OPERATIONS }),
      'GET /pharmacy/alerts': () => ({ body: STOCK }),
    });
  }

  it('keeps the backend’s order — longest wait, not busiest', async () => {
    signInAs('admin');
    stub();
    renderWithProviders(<OperationsPage />);

    await screen.findByText('Kayachikitsa', { exact: false });
    const table = screen.getByTestId('department-load');
    const rows = within(table).getAllByRole('row').slice(1);
    // General has more people waiting; kayachikitsa has the person who has been
    // there longest, and that is the row an administrator is looking for.
    expect(rows[0]?.getAttribute('data-department')).toBe('kayachikitsa');
    expect(rows[1]?.getAttribute('data-department')).toBe('general');
  });

  it('separates an expired box from an empty shelf', async () => {
    signInAs('admin');
    stub();
    renderWithProviders(<OperationsPage />);

    const expired = (await screen.findByText('ORS sachet')).closest('li');
    const panel = screen.getByTestId('stock-alerts');
    const out = within(panel).getByText('Pantoprazole 40 mg').closest('li');
    expect(panel.contains(expired)).toBe(true);
    expect(expired?.querySelector('[data-stock-state="expired"]')).toBeTruthy();
    expect(out?.querySelector('[data-stock-state="out"]')).toBeTruthy();
  });

  it('says that an unlisted medicine is not a medicine that ran out', async () => {
    signInAs('admin');
    stub();
    renderWithProviders(<OperationsPage />);

    const panel = await screen.findByTestId('stock-alerts');
    // The one thing this list cannot show, stated rather than left to inference.
    expect(within(panel).getByText(/never been told about/i)).toBeTruthy();
  });

  it('shows an empty pharmacy as nothing to do, not as a failure', async () => {
    signInAs('admin');
    stubFetch({
      'GET /operations': () => ({ body: { generated_at: OPERATIONS.generated_at, departments: [] } }),
      'GET /pharmacy/alerts': () => ({ body: { generated_at: STOCK.generated_at, alerts: [] } }),
    });
    renderWithProviders(<OperationsPage />);

    expect(await screen.findByText(/nothing needs attention/i)).toBeTruthy();
    expect(screen.getByText(/nobody is waiting/i)).toBeTruthy();
  });
});
