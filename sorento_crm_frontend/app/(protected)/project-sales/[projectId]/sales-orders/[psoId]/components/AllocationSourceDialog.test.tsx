/**
 * P9 - the ranked source picker (AC-H1 to AC-H4).
 *
 * The one thing that must never regress is the difference between stock nobody has spoken
 * for and stock held for another project. Free stock is USED: it takes a quantity and goes
 * into the basket. Held stock is ASKED for: it offers a Request and no quantity box at all,
 * because until that project's CS answers, nothing moves. A quantity box on a held pile is
 * the UI telling somebody they may take what they may not.
 *
 * The ranking itself is the backend's; the dialog renders it in the order it arrived and
 * never re-sorts, so the order on screen is asserted against the order in the payload.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  AllocationCandidate,
  AllocationCandidateList,
  AllocationLineRow,
} from '../../../../_shared/types/projectAllocation.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

const listAllocationCandidates = vi.fn();

vi.mock('../../../../_shared/services/projectAllocationService', () => ({
  listSalesOrderAllocations: vi.fn(),
  listAllocationCandidates: (...args: unknown[]) => listAllocationCandidates(...args),
  confirmAllocation: vi.fn(),
  clearAllocation: vi.fn(),
  raiseAllocationClaim: vi.fn(),
  listAllocationClaims: vi.fn(),
  acceptAllocationClaim: vi.fn(),
  refuseAllocationClaim: vi.fn(),
}));

import { AllocationSourceDialog } from './AllocationSourceDialog';

const LINE: AllocationLineRow = {
  line_id: 'l1',
  line_no: 7,
  product_id: 'prod-1',
  product_code: 'SRT382-6',
  description: 'SORENTO STAINLESS STEEL FLOOR GRATING 6" x 6"',
  qty: '10',
  uom: 'UNIT',
  delivery_date: '2026-07-01',
  state: 'unallocated',
  stock_location: null,
  allocated_qty: '0',
  outstanding_qty: '10',
  sources: [],
};

function candidate(overrides: Partial<AllocationCandidate> = {}): AllocationCandidate {
  return {
    rank: 1,
    source_type: 'brw',
    warehouse_id: 'wh-brw',
    warehouse_code: 'BRW',
    warehouse_name: 'Master location',
    on_hand: '100',
    reserved: '0',
    held_for_this_project: '0',
    held_for_other_projects: '0',
    committed: '0',
    available: '100',
    allocatable: '100',
    claimable: '0',
    requires_claim: false,
    is_project_location: false,
    holders: [],
    open_claim_id: null,
    open_claim_state: null,
    ...overrides,
  };
}

/** The four ranks the backend returns, in the order it returns them. */
const BRW = candidate();
const OWN_PROJECT = candidate({
  rank: 2,
  source_type: 'own',
  warehouse_id: 'wh-prj',
  warehouse_code: 'WH-PRJ',
  is_project_location: true,
  on_hand: '30',
  available: '30',
  allocatable: '30',
});
const HELD = candidate({
  rank: 3,
  source_type: 'other_project',
  warehouse_id: 'wh-kl',
  warehouse_code: 'WH-KL',
  on_hand: '40',
  committed: '40',
  held_for_other_projects: '40',
  available: '0',
  allocatable: '0',
  claimable: '40',
  requires_claim: true,
  holders: [
    { project_id: 'p2', project_code: 'PRJ-000042', cs_name: 'Aisyah', qty: '40' },
  ],
});
const ORDER = candidate({
  rank: 4,
  source_type: 'order',
  warehouse_id: null,
  warehouse_code: null,
  on_hand: '0',
  available: '0',
  allocatable: '0',
});

function payload(overrides: Partial<AllocationCandidateList> = {}): AllocationCandidateList {
  return {
    line_id: 'l1',
    line_no: 7,
    product_code: 'SRT382-6',
    description: 'SORENTO STAINLESS STEEL FLOOR GRATING 6" x 6"',
    qty: '10',
    uom: 'UNIT',
    delivery_date: '2026-07-01',
    project_code: 'PRJ-000001',
    brw_warehouse_code: 'BRW',
    candidates: [BRW, OWN_PROJECT, HELD, ORDER],
    plan: [],
    shortfall: '0',
    covered: false,
    ...overrides,
  };
}

const onConfirm = vi.fn();
const onClaim = vi.fn();
const onDone = vi.fn();

function renderDialog(props: { canEdit?: boolean; submitting?: boolean } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AllocationSourceDialog
        line={LINE}
        canEdit={props.canEdit ?? true}
        submitting={props.submitting ?? false}
        onDone={onDone}
        onConfirm={onConfirm}
        onClaim={onClaim}
      />
    </QueryClientProvider>,
  );
}

/** The card for one location, so a Request and a quantity box can be told apart. */
function cardFor(warehouseCode: string): HTMLElement {
  const label = screen.getByTitle(warehouseCode);
  const card = label.closest('div.rounded-lg');
  if (!card) throw new Error(`No candidate card for ${warehouseCode}`);
  return card as HTMLElement;
}

/** Ordering it is the one candidate with no location of its own. */
function orderCard(): HTMLElement {
  const card = screen.getByText('No location').closest('div.rounded-lg');
  if (!card) throw new Error('No candidate card for ordering it');
  return card as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  onConfirm.mockResolvedValue(undefined);
  onClaim.mockResolvedValue(undefined);
  listAllocationCandidates.mockResolvedValue(payload());
});

describe('AllocationSourceDialog', () => {
  it('names the line and its quantity in the title', async () => {
    renderDialog();

    expect(await screen.findByText('Line 7: SRT382-6')).toBeInTheDocument();
    expect(screen.getByText('10 UNIT')).toBeInTheDocument();
  });

  it('shows placeholders while the live figures are being read, not a stale list', () => {
    listAllocationCandidates.mockReturnValue(new Promise(() => {}));

    renderDialog();

    // The dialog is portalled out of the render container, so it is queried by role.
    const dialog = screen.getByRole('dialog');
    expect(dialog.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.queryByText('BRW')).not.toBeInTheDocument();
  });

  it('says the ranked sources could not be read rather than showing none', async () => {
    listAllocationCandidates.mockRejectedValue(new Error('Stock service is down'));

    renderDialog();

    expect(
      await screen.findByText('The ranked sources could not be loaded'),
    ).toBeInTheDocument();
    expect(screen.getByText('Stock service is down')).toBeInTheDocument();
  });

  it('says the product is nowhere on the shelf and points at ordering it', async () => {
    listAllocationCandidates.mockResolvedValue(payload({ candidates: [] }));

    renderDialog();

    expect(await screen.findByText('No location holds this product')).toBeInTheDocument();
    expect(
      screen.getByText('It has to be ordered. Put the full quantity against Order it below.'),
    ).toBeInTheDocument();
  });

  it('keeps the ranking the backend sent, master location first and ordering it last', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    const dialog = screen.getByRole('dialog');
    const codes = Array.from(dialog.querySelectorAll('span[title]')).map((node) =>
      node.getAttribute('title'),
    );
    expect(codes).toEqual(['BRW', 'WH-PRJ', 'WH-KL', '']);

    const ranks = Array.from(dialog.querySelectorAll('[data-slot="badge"]'))
      .map((node) => node.textContent)
      .filter((text) => text && /^\d+$/.test(text));
    expect(ranks).toEqual(['1', '2', '3', '4']);
  });

  it('marks this project own location so it is not mistaken for anyone else', async () => {
    renderDialog();
    await screen.findByTitle('WH-PRJ');

    expect(within(cardFor('WH-PRJ')).getByText('This project')).toBeInTheDocument();
    expect(within(cardFor('BRW')).queryByText('This project')).not.toBeInTheDocument();
  });

  it('held stock offers a request, not a quantity box', async () => {
    renderDialog();
    await screen.findByTitle('WH-KL');

    const held = within(cardFor('WH-KL'));
    expect(held.getByRole('button', { name: 'Request from PRJ-000042' })).toBeInTheDocument();
    // The single most important assertion on this screen: held stock cannot be typed into.
    expect(held.queryByLabelText('Take')).not.toBeInTheDocument();

    const free = within(cardFor('BRW'));
    expect(free.getByLabelText('Take')).toBeInTheDocument();
    expect(free.queryByRole('button', { name: /^Request from/ })).not.toBeInTheDocument();
  });

  it('names the project holding the stock, its CS, and shows nothing free there', async () => {
    renderDialog();
    await screen.findByTitle('WH-KL');

    const held = within(cardFor('WH-KL'));
    expect(held.getByText('40 held for PRJ-000042, ask Aisyah')).toBeInTheDocument();
    expect(held.getByText('On hand 40 · committed 40 · free 0')).toBeInTheDocument();
    expect(held.getByText('Held for another project')).toBeInTheDocument();
  });

  it('asks the holding project only for what the line needs, not for their whole pile', async () => {
    // The line needs 10 and PRJ-000042 is holding 40. Asking for 40 put a request for
    // four times the requirement into another CS's inbox, and with two holders on one
    // candidate both buttons asked for the same 40.
    renderDialog();
    await screen.findByTitle('WH-KL');

    fireEvent.click(
      within(cardFor('WH-KL')).getByRole('button', { name: 'Request from PRJ-000042' }),
    );

    await waitFor(() =>
      expect(onClaim).toHaveBeenCalledWith({
        warehouse_id: 'wh-kl',
        to_project_id: 'p2',
        qty: '10',
      }),
    );
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    // Asking is not taking: nothing was confirmed onto the line.
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('will not let a location be drawn past what it actually holds', async () => {
    // The line total was checked but the per-location figure was not, so 500 could be
    // typed against a shelf holding 30 and Confirm stayed live. The server refuses it;
    // finding that out after pressing Confirm is a worse way to learn.
    renderDialog();
    await screen.findByTitle('BRW');

    fireEvent.change(within(cardFor('BRW')).getByLabelText('Take'), {
      target: { value: '9999' },
    });

    expect(screen.getByRole('button', { name: /Confirm/i })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('refuses a second ask while the first is unanswered, and says why', async () => {
    listAllocationCandidates.mockResolvedValue(
      payload({
        candidates: [
          BRW,
          { ...HELD, open_claim_id: 'c1', open_claim_state: 'requested' },
        ],
      }),
    );

    renderDialog();
    await screen.findByTitle('WH-KL');

    const held = within(cardFor('WH-KL'));
    expect(held.getByText('Already asked for. Waiting on an answer.')).toBeInTheDocument();
    expect(held.getByRole('button', { name: 'Request from PRJ-000042' })).toBeDisabled();
  });

  it('pre-fills the proposal the backend planned so it is edited, not typed from nothing', async () => {
    listAllocationCandidates.mockResolvedValue(
      payload({ plan: [{ warehouse_id: 'wh-brw', warehouse_code: 'BRW', qty: '10' }] }),
    );

    renderDialog();
    await screen.findByTitle('BRW');

    await waitFor(() =>
      expect(within(cardFor('BRW')).getByLabelText('Take')).toHaveValue('10'),
    );
    expect(await screen.findByText('All 10 sourced.')).toBeInTheDocument();
  });

  it('puts the shortfall against ordering it when the shelves cannot cover the line', async () => {
    listAllocationCandidates.mockResolvedValue(
      payload({
        plan: [{ warehouse_id: 'wh-brw', warehouse_code: 'BRW', qty: '6' }],
        shortfall: '4',
      }),
    );

    renderDialog();
    await screen.findByTitle('BRW');

    await waitFor(() =>
      expect(within(orderCard()).getByLabelText('Take')).toHaveValue('4'),
    );
  });

  it('confirms one source with the location and quantity that was typed', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    fireEvent.change(within(cardFor('BRW')).getByLabelText('Take'), {
      target: { value: '10' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Confirm source/ }));

    await waitFor(() =>
      expect(onConfirm).toHaveBeenCalledWith([
        { source_type: 'brw', warehouse_id: 'wh-brw', qty: '10' },
      ]),
    );
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it('sends both legs when a line is split across two locations', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    fireEvent.change(within(cardFor('BRW')).getByLabelText('Take'), {
      target: { value: '6' },
    });
    fireEvent.change(within(cardFor('WH-PRJ')).getByLabelText('Take'), {
      target: { value: '4' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Confirm source/ }));

    await waitFor(() =>
      expect(onConfirm).toHaveBeenCalledWith([
        { source_type: 'brw', warehouse_id: 'wh-brw', qty: '6' },
        { source_type: 'own', warehouse_id: 'wh-prj', qty: '4' },
      ]),
    );
  });

  it('sends ordering it as a source that carries no location', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    fireEvent.change(within(orderCard()).getByLabelText('Take'), {
      target: { value: '10' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Confirm source/ }));

    await waitFor(() =>
      expect(onConfirm).toHaveBeenCalledWith([{ source_type: 'order', qty: '10' }]),
    );
  });

  it('never puts held stock into the basket, whatever else is confirmed', async () => {
    renderDialog();
    await screen.findByTitle('WH-KL');

    fireEvent.change(within(cardFor('BRW')).getByLabelText('Take'), {
      target: { value: '10' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Confirm source/ }));

    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
    const sources = onConfirm.mock.calls[0][0] as { source_type: string }[];
    expect(sources.some((row) => row.source_type === 'other_project')).toBe(false);
  });

  it('counts what is still open as the quantities are typed', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    expect(screen.getByText('0 of 10 sourced, 10 still open.')).toBeInTheDocument();

    fireEvent.change(within(cardFor('BRW')).getByLabelText('Take'), {
      target: { value: '4' },
    });
    expect(screen.getByText('4 of 10 sourced, 6 still open.')).toBeInTheDocument();
  });

  it('refuses to confirm more than the line needs, and says by how much', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    fireEvent.change(within(cardFor('BRW')).getByLabelText('Take'), {
      target: { value: '12' },
    });

    expect(screen.getByText('That is 2 more than the line needs.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm source/ })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('confirms nothing while nothing has been chosen', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    expect(screen.getByRole('button', { name: /Confirm source/ })).toBeDisabled();
  });

  it('lets a reader look at the ranking without taking or asking for anything', async () => {
    renderDialog({ canEdit: false });
    await screen.findByTitle('BRW');

    expect(within(cardFor('BRW')).getByLabelText('Take')).toBeDisabled();
    expect(
      within(cardFor('WH-KL')).getByRole('button', { name: 'Request from PRJ-000042' }),
    ).toBeDisabled();
    expect(screen.getByRole('button', { name: /Confirm source/ })).toBeDisabled();
  });

  it('closes on cancel without writing anything', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onDone).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onClaim).not.toHaveBeenCalled();
  });

  it('blocks a second submit while the first is in flight', async () => {
    renderDialog({ submitting: true });
    await screen.findByTitle('BRW');

    expect(screen.getByRole('button', { name: /Confirm source/ })).toBeDisabled();
    expect(within(cardFor('BRW')).getByLabelText('Take')).toBeDisabled();
    expect(
      within(cardFor('WH-KL')).getByRole('button', { name: 'Request from PRJ-000042' }),
    ).toBeDisabled();
  });
});
