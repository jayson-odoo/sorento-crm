/**
 * P9 - the ranked sources, as evidence (AC-H1, AC-H2). Read-only since Stage 1C.
 *
 * The dialog answers "what could this line come from, and who is holding it". It takes no
 * decision: supply is composed and confirmed for the whole sales order in Fulfilment
 * Planning, so a quantity box or a Request button here would be a decision with nowhere to
 * go - the backend routes behind them are gone.
 *
 * The ranking itself is the backend's; the dialog renders it in the order it arrived and
 * never re-sorts, so the order on screen is asserted against the order in the payload.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
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
  listAllocationClaims: vi.fn(),
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

const onDone = vi.fn();

function renderDialog() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AllocationSourceDialog line={LINE} onDone={onDone} />
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
      screen.getByText('It has to be bought. The Buy residual is decided in Fulfilment Planning.'),
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

  it('names the project holding the stock, its CS, and shows nothing free there', async () => {
    renderDialog();
    await screen.findByTitle('WH-KL');

    const held = within(cardFor('WH-KL'));
    expect(held.getByText('40 held for PRJ-000042, ask Aisyah')).toBeInTheDocument();
    expect(held.getByText('On hand 40 · committed 40 · free 0')).toBeInTheDocument();
    expect(held.getByText('Held for another project')).toBeInTheDocument();
  });

  it('states what each location has free to take, and asks for nothing', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    expect(within(cardFor('BRW')).getByText('100')).toBeInTheDocument();
    expect(within(cardFor('WH-PRJ')).getByText('30')).toBeInTheDocument();
    expect(screen.getAllByText('free to take').length).toBe(3);
  });

  it('says purchasing buys the order candidate, and gives it no shelf figure', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    const order = within(orderCard());
    expect(order.getByText('Nothing on the shelf covers this. Purchasing buys it.')).toBeInTheDocument();
    expect(order.queryByText('free to take')).not.toBeInTheDocument();
  });

  it('takes no quantity and asks for nothing, on free stock or on held stock', async () => {
    // The routes behind both are gone: a Take box or a Request button here would be a
    // decision the backend has nowhere to put.
    renderDialog();
    await screen.findByTitle('WH-KL');

    expect(screen.queryByLabelText('Take')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Request from/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Confirm source/ })).not.toBeInTheDocument();
  });

  it('says where supply is composed, and offers the way there', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    expect(screen.getByText('Supply is composed in Fulfilment Planning.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open fulfilment planning/i })).toHaveAttribute(
      'href',
      '/project-sales/fulfilment-planning',
    );
  });

  it('closes on Close', async () => {
    renderDialog();
    await screen.findByTitle('BRW');

    // The dialog chrome carries its own X, also named Close; the footer one is last.
    const closes = screen.getAllByRole('button', { name: 'Close' });
    fireEvent.click(closes[closes.length - 1]);

    expect(onDone).toHaveBeenCalled();
  });
});
