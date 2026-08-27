/**
 * The already-converted state's Delete action (`PLAN-scm-proforma-to-spo.md`'s third
 * amendment, captain live case 21 Aug): the AlertDialog names the SPO numbers and count
 * per ADR-PRODUCT-STANDARDS, the delete actually fires the DELETE route, and a self-heal
 * note (a stale link cleaned up on read) shows as an informational banner rather than a
 * toast. The confirm-table (non-converted) path is exercised by `CreateSpoPanel.test.tsx`'s
 * older sibling; this file covers what changed on `SpoPlannerTable` itself.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const suggestionFn: (...args: unknown[]) => Promise<unknown> = () => Promise.resolve(state.suggestion);

const state = {
  suggestion: null as unknown,
  suggestionFn,
  create: vi.fn(),
  deleteSpo: vi.fn(),
  worksheet: vi.fn(),
};

/** The two lightbox bodies that FETCH (On hand, Incoming SPO) - mocked at the hook, so these
 *  tests are about what the planner opens, not about react-query's timing. */
const useLocationStock = vi.fn();
vi.mock('@/app/(protected)/scm/reorder/hooks/useReorderRun', () => ({
  useLocationStock: (...a: unknown[]) => useLocationStock(...a),
}));

const useContainerRequestDrill = vi.fn();
vi.mock('@/app/(protected)/scm/hooks/useContainerRequestDrill', () => ({
  useContainerRequestDrill: (...a: unknown[]) => useContainerRequestDrill(...a),
}));

vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  getSpoSuggestion: (...args: unknown[]) => state.suggestionFn(...args),
  createSpo: (...args: unknown[]) => state.create(...args),
  deleteSpo: (...args: unknown[]) => state.deleteSpo(...args),
  downloadSpoWorksheet: (...args: unknown[]) => state.worksheet(...args),
}));

import { toast } from 'sonner';
import { NO_SPO_TO_POOL } from '@/app/(protected)/scm/components/PlanRowDialog';
import { SpoPlannerTable } from './SpoPlannerTable';

function suggestion(over: Record<string, unknown> = {}) {
  return {
    shipment_id: 'sh-1',
    shipment_number: 'ABCU1000001',
    shipment_status: 'in_transit',
    already_converted: false,
    existing_spos: [],
    lines: [],
    self_heal_note: null,
    ...over,
  };
}

function renderTable() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SpoPlannerTable shipmentId="sh-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  state.suggestion = suggestion();
  state.suggestionFn = () => Promise.resolve(state.suggestion);
  state.deleteSpo = vi.fn().mockResolvedValue({
    shipment_id: 'sh-1',
    shipment_number: 'ABCU1000001',
    deleted_po_numbers: ['CRM-SPO-0001'],
    deleted_spo_count: 1,
    deleted_allocation_count: 0,
  });
  state.worksheet = vi.fn().mockResolvedValue(undefined);
  useLocationStock.mockReturnValue({ data: undefined, isLoading: false });
  useContainerRequestDrill.mockReturnValue({
    data: { kind: 'spo', rows: [], total: 0, history: [] },
    isLoading: false,
  });
});

const existingSpos = () => [
  { purchase_order_id: 'po-1', po_number: 'CRM-SPO-0001', supplier_id: 'sup-1', supplier_name: 'Kailu' },
];

describe('SpoPlannerTable - already-converted Delete action', () => {
  it('offers a Delete SPO action alongside the worksheet download', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    renderTable();

    expect(await screen.findByRole('button', { name: /delete spo/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download worksheet/i })).toBeInTheDocument();
  });

  it('names the SPO number and uses the standard "cannot be undone" copy in the confirm dialog', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));

    expect(await screen.findByText('Confirm delete')).toBeInTheDocument();
    expect(screen.getByText(/This deletes CRM-SPO-0001/)).toBeInTheDocument();
    expect(screen.getByText(/This action cannot be undone/)).toBeInTheDocument();
  });

  it('names every SPO and the count when more than one was created from this shipment', async () => {
    state.suggestion = suggestion({
      already_converted: true,
      existing_spos: [
        ...existingSpos(),
        { purchase_order_id: 'po-2', po_number: 'CRM-SPO-0002', supplier_id: 'sup-2', supplier_name: 'Jiangmen' },
      ],
    });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));

    expect(
      await screen.findByText(/This deletes 2 SPOs: CRM-SPO-0001, CRM-SPO-0002/),
    ).toBeInTheDocument();
  });

  it('does not delete until the AlertDialog is confirmed', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));
    await screen.findByText('Confirm delete');

    expect(state.deleteSpo).not.toHaveBeenCalled();
  });

  it('deletes on confirm and toasts the deleted SPO number', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));
    await screen.findByText('Confirm delete');
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));

    await waitFor(() => expect(state.deleteSpo).toHaveBeenCalledWith('sh-1'));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Deleted SPO CRM-SPO-0001.'),
    );
  });

  it('closes the dialog on cancel without deleting anything', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));
    await screen.findByText('Confirm delete');
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    await waitFor(() => expect(screen.queryByText('Confirm delete')).not.toBeInTheDocument());
    expect(state.deleteSpo).not.toHaveBeenCalled();
  });

  it('surfaces the crm_spo-only guard message as an error toast on a refused delete', async () => {
    state.suggestion = suggestion({ already_converted: true, existing_spos: existingSpos() });
    state.deleteSpo = vi.fn().mockRejectedValue(
      new Error('CRM-SPO-0001 was not created by Create SPO and cannot be deleted from this screen.'),
    );
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /delete spo/i }));
    await screen.findByText('Confirm delete');
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'CRM-SPO-0001 was not created by Create SPO and cannot be deleted from this screen.',
      ),
    );
  });

  it('shows a self-heal note as an informational banner, not a toast', async () => {
    state.suggestion = suggestion({
      already_converted: true,
      existing_spos: existingSpos(),
      self_heal_note: '1 SPO previously linked to this shipment no longer exists and has been cleared.',
    });
    renderTable();

    expect(
      await screen.findByText(/no longer exists and has been cleared/),
    ).toBeInTheDocument();
    expect(toast.warning).not.toHaveBeenCalled();
    expect(toast.info).not.toHaveBeenCalled();
  });
});

/**
 * F7 - the planner CHOOSES: which POs it draws from, and which demand it is for.
 *
 * One line, two POs and three pieces of demand, so every default and every untick has a
 * figure that can only come from one of them.
 */
function plannerLine(over: Record<string, unknown> = {}) {
  return {
    shipment_line_id: 'sl-1',
    product_id: 'p-1',
    item_code: 'SRTWT7443',
    product_name: 'Basin Mixer',
    supplier_id: 'sup-1',
    supplier_name: 'Kailu',
    packed_qty: 100,
    po_covered_qty: 100,
    matched_po_number: '202605-S0060',
    matched_by: 'product' as const,
    po_takes: [
      {
        po_line_id: 'pol-1',
        po_number: '202605-S0060',
        qty: 60,
        expected_date: '2026-09-01',
        po_date: '2026-05-02',
        supplier_name: 'Kailu',
        open_qty: 60,
      },
      {
        po_line_id: 'pol-2',
        po_number: '202606-S0099',
        qty: 40,
        expected_date: '2026-08-01',
        po_date: '2026-06-11',
        supplier_name: 'Kailu',
        // 150 open, of which the cascade took 40 - so unticking the FIRST take does not
        // lose 60, it asks this line for the whole 100 (review finding 9).
        open_qty: 150,
      },
    ],
    on_hand: 0,
    incoming_spo: 0,
    suggested_qty: 100,
    no_po_qty: 0,
    cannot_convert: false,
    reason: null,
    unit_cost: 12,
    currency: 'CNY',
    location_options: [
      {
        warehouse_id: 'wh-1',
        warehouse_code: 'BRW',
        outstanding_so: 70,
        on_hand: 0,
        incoming_spo: 0,
        available: -70,
        rank_score: 1,
        demand_lines: [],
      },
      {
        warehouse_id: 'wh-2',
        warehouse_code: 'MWH',
        outstanding_so: 30,
        on_hand: 0,
        incoming_spo: 0,
        available: -30,
        rank_score: 0.5,
        demand_lines: [],
      },
    ],
    suggested_warehouse_id: 'wh-1',
    so_coverage: [
      {
        key: 'project:row-1',
        kind: 'project' as const,
        document: 'SI26-0100',
        customer_name: 'Sunway',
        required_date: '2026-09-10',
        qty: 40,
        warehouse_id: 'wh-1',
        warehouse_code: 'BRW',
        default_ticked: true,
      },
      {
        key: 'retail:sol-9',
        kind: 'retail' as const,
        document: 'SO-2201',
        customer_name: 'Dealer A',
        required_date: '2026-09-20',
        qty: 30,
        warehouse_id: 'wh-2',
        warehouse_code: 'MWH',
        default_ticked: true,
      },
      {
        key: 'retail:sol-10',
        kind: 'retail' as const,
        document: 'SO-2202',
        customer_name: 'Dealer B',
        required_date: '2026-10-02',
        qty: 90,
        warehouse_id: 'wh-2',
        warehouse_code: 'MWH',
        default_ticked: false,
      },
    ],
    ...over,
  };
}

describe('F7 - the SPO planner chooses its POs and its SOs', () => {
  beforeEach(() => {
    state.suggestion = suggestion({ lines: [plannerLine()] });
    state.create = vi.fn().mockResolvedValue({
      shipment_id: 'sh-1',
      shipment_number: 'ABCU1000001',
      created_spos: [],
      skipped: [],
      allocations: [],
      demand_links: [],
    });
  });

  const openPoDrill = async () =>
    fireEvent.click(await screen.findByTitle(/which po covers this/i));
  const openSoDrill = async () =>
    fireEvent.click(await screen.findByTitle(/which demand this spo is for/i));

  it('ticks every PO take by default and says how many (AC-G1)', async () => {
    renderTable();

    expect(await screen.findByText('2 of 2 POs')).toBeInTheDocument();
    await openPoDrill();
    expect(screen.getByRole('checkbox', { name: 'Draw from 202605-S0060' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Draw from 202606-S0099' })).toBeChecked();
  });

  it('unticking a take re-cascades over the POs still ticked (AC-G2)', async () => {
    renderTable();
    await openPoDrill();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Draw from 202605-S0060' }));

    expect(await screen.findByText('1 of 2 POs')).toBeInTheDocument();
    // The remaining PO has 150 open, so it covers the whole 100 packed - not the 40 the
    // cascade happened to take from it while the other one was ticked.
    expect(screen.getByTitle(/what the TICKED POs pull this SPO up to/i)).toHaveValue(100);
  });

  it('a take can only cover what its own line has open', async () => {
    state.suggestion = suggestion({
      lines: [plannerLine({ packed_qty: 200, po_covered_qty: 100, suggested_qty: 100 })],
    });
    renderTable();
    await openPoDrill();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Draw from 202606-S0099' }));

    // Only the 60-open line is ticked now, whatever the packed quantity is.
    expect(screen.getByTitle(/what the TICKED POs pull this SPO up to/i)).toHaveValue(60);
  });

  it('sends only the ticked takes to the create (AC-G6)', async () => {
    renderTable();
    await openPoDrill();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Draw from 202605-S0060' }));
    fireEvent.click(screen.getByRole('button', { name: /create spo/i }));

    await waitFor(() => expect(state.create).toHaveBeenCalledTimes(1));
    const [, lines] = state.create.mock.calls[0];
    expect(lines[0].po_take_ids).toEqual(['pol-2']);
    expect(lines[0].qty).toBe(100);
  });

  it("pre-ticks the server's demand walk, and leaves the rest untouched (AC-G3)", async () => {
    renderTable();
    await openSoDrill();

    expect(screen.getByRole('checkbox', { name: 'Cover SI26-0100' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Cover SO-2201' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Cover SO-2202' })).not.toBeChecked();
  });

  it('states what no tick claims as unassigned (Q4, AC-G4)', async () => {
    renderTable();
    await openSoDrill();

    // 100 packed, 40 + 30 ticked - the remaining 30 is free stock. Said in the lightbox's
    // footer, and again on the location cell, because that is where it decides where goods
    // land.
    expect(screen.getByText('Unassigned 30')).toBeInTheDocument();
    expect(screen.getByText(/30 unassigned/)).toBeInTheDocument();
  });

  it('the ticks drive the location split (AC-G4)', async () => {
    renderTable();
    fireEvent.click(await screen.findByRole('button', { name: /create spo/i }));

    await waitFor(() => expect(state.create).toHaveBeenCalledTimes(1));
    const [, lines] = state.create.mock.calls[0];
    // 40 to the project row's BRW, 30 to the retail line's MWH, and the unassigned 30 to
    // the suggested warehouse, which is BRW.
    expect(lines[0].location_splits).toEqual([
      { warehouse_id: 'wh-1', qty: 70 },
      { warehouse_id: 'wh-2', qty: 30 },
    ]);
    expect(lines[0].so_line_ids).toEqual(['project:row-1', 'retail:sol-9']);
  });

  it('re-splits when a tick changes', async () => {
    renderTable();
    await openSoDrill();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Cover SO-2201' }));
    fireEvent.click(screen.getByRole('button', { name: /create spo/i }));

    await waitFor(() => expect(state.create).toHaveBeenCalledTimes(1));
    const [, lines] = state.create.mock.calls[0];
    // Only the project row is ticked now: 40 at BRW, and 60 unassigned at the same BRW.
    expect(lines[0].location_splits).toEqual([{ warehouse_id: 'wh-1', qty: 100 }]);
    expect(lines[0].so_line_ids).toEqual(['project:row-1']);
  });

  it('states the shortfall when the ticks ask for more than the container holds (AC-G5)', async () => {
    renderTable();
    await openSoDrill();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Cover SO-2202' }));

    // 160 ticked against a container of 100: the third order is served in part, which is
    // what the default walk does on its last entry every time. Said out loud, not blocked.
    expect(
      await screen.findByText(/160 ticked, 100 on this container - SO-2202 partly covered/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create spo/i })).toBeEnabled();
  });
});

/**
 * Browser pass 2, finding 3 - the banner and the cell must be the same arithmetic.
 *
 * The shape the tester hit on SHIP-DRAFT-18cdfe5e: a container packed with 100 whose open
 * POs only cover 19, against a product with far more open demand than either figure. The
 * SO-covered cell read 19 (right), and the banner read "302 ticked against 100 packed" and
 * disabled Create SPO (wrong - nothing was over-ticked, the default walk simply includes
 * the order it can only partly serve).
 */
function shortCoveredLine(over: Record<string, unknown> = {}) {
  return plannerLine({
    shipment_line_id: 'sl-short',
    item_code: 'CGB247',
    packed_qty: 100,
    po_covered_qty: 19,
    suggested_qty: 19,
    po_takes: [
      {
        po_line_id: 'pol-short',
        po_number: '202605-S0060',
        qty: 19,
        expected_date: '2026-09-01',
        po_date: '2026-05-02',
        supplier_name: 'Jinbaichuan',
        open_qty: 19,
      },
    ],
    so_coverage: [
      {
        key: 'project:row-a',
        kind: 'project' as const,
        document: 'SI26-0100',
        customer_name: 'Sunway',
        required_date: '2026-09-10',
        qty: 12,
        warehouse_id: 'wh-1',
        warehouse_code: 'BRW',
        default_ticked: true,
      },
      {
        key: 'retail:sol-a',
        kind: 'retail' as const,
        document: 'SO-2201',
        customer_name: 'Dealer A',
        required_date: '2026-09-20',
        qty: 90,
        warehouse_id: 'wh-2',
        warehouse_code: 'MWH',
        default_ticked: true,
      },
      {
        key: 'retail:sol-b',
        kind: 'retail' as const,
        document: 'SO-2202',
        customer_name: 'Dealer B',
        required_date: '2026-10-02',
        qty: 200,
        warehouse_id: 'wh-2',
        warehouse_code: 'MWH',
        default_ticked: false,
      },
    ],
    ...over,
  });
}

describe('F7 - the SO-covered cell and the Create banner are one arithmetic', () => {
  beforeEach(() => {
    state.suggestion = suggestion({ lines: [shortCoveredLine()] });
    state.create = vi.fn().mockResolvedValue({
      shipment_id: 'sh-1',
      shipment_number: 'ABCU1000001',
      created_spos: [],
      skipped: [],
      allocations: [],
      demand_links: [],
    });
  });

  it('does not accuse the default ticks of over-ticking the container', async () => {
    renderTable();

    expect(await screen.findByRole('button', { name: /create spo/i })).toBeEnabled();
    expect(screen.queryByText(/ticked against/)).not.toBeInTheDocument();
  });

  it('the cell states what the ticks actually cover, not what they asked for', async () => {
    renderTable();

    // 19 is all this SPO can pull, so 19 is what the ticked orders get between them.
    const soCell = await screen.findByTitle(/which demand this spo is for/i);
    expect(soCell).toHaveTextContent('19');
    expect(soCell).not.toHaveTextContent('102');
  });

  it('ticks only as far down the list as the SPO can actually serve', async () => {
    renderTable();
    fireEvent.click(await screen.findByTitle(/which demand this spo is for/i));

    // 12 to the first, 7 of the second's 90 - and the third is out of reach entirely.
    expect(screen.getByRole('checkbox', { name: 'Cover SI26-0100' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Cover SO-2201' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Cover SO-2202' })).not.toBeChecked();
  });

  it('says which order it cannot serve when the operator ticks one it cannot reach', async () => {
    renderTable();
    fireEvent.click(await screen.findByTitle(/which demand this spo is for/i));

    fireEvent.click(screen.getByRole('checkbox', { name: 'Cover SO-2202' }));

    // Named on the banner - the lightbox lists SO-2202 as well, so the assertion is on the
    // sentence that stops the send, not on the number appearing somewhere.
    expect(
      await screen.findByText(/SO-2202 - this container has nothing left/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create spo/i })).toBeDisabled();
  });

  it('splits only what it can serve, and calls the rest unassigned', async () => {
    renderTable();
    fireEvent.click(await screen.findByRole('button', { name: /create spo/i }));

    await waitFor(() => expect(state.create).toHaveBeenCalledTimes(1));
    const [, lines] = state.create.mock.calls[0];
    expect(lines[0].qty).toBe(19);
    expect(lines[0].location_splits).toEqual([
      { warehouse_id: 'wh-1', qty: 12 },
      { warehouse_id: 'wh-2', qty: 7 },
    ]);
  });
});

/**
 * Browser pass 3, finding 2 - a tick and an untick are the same recompute.
 *
 * Untick a take and everything follows: the cover, the SPO qty, the SO covered, the split.
 * Re-tick it and the cell went back to 66 / "4 of 4 POs" while every figure downstream
 * stayed at the unticked value until a reload.
 */
describe('F7 - unticking then re-ticking a take returns every figure', () => {
  beforeEach(() => {
    state.suggestion = suggestion({ lines: [plannerLine()] });
    state.create = vi.fn().mockResolvedValue({
      shipment_id: 'sh-1',
      shipment_number: 'ABCU1000001',
      created_spos: [],
      skipped: [],
      allocations: [],
      demand_links: [],
    });
  });

  const qtyInput = () => screen.getByTitle(/what the TICKED POs pull this SPO up to/i);
  /** The drill closes on a tick, so each one is its own open-click-read. */
  const tick = async (name: string) => {
    fireEvent.click(await screen.findByTitle(/which po covers this/i));
    fireEvent.click(screen.getByRole('checkbox', { name }));
  };

  it('puts the SPO quantity back when the take is ticked again', async () => {
    renderTable();
    await screen.findByTitle(/which po covers this/i);

    expect(qtyInput()).toHaveValue(100);
    await tick('Draw from 202605-S0060');
    // The 150-open line covers the whole 100 on its own.
    expect(qtyInput()).toHaveValue(100);
    await tick('Draw from 202606-S0099');
    expect(qtyInput()).toHaveValue(0);

    await tick('Draw from 202606-S0099');

    expect(qtyInput()).toHaveValue(100);
    await tick('Draw from 202605-S0060');
    expect(screen.getByText('2 of 2 POs')).toBeInTheDocument();
    expect(qtyInput()).toHaveValue(100);
  });

  it('puts the split and what is sent back with it', async () => {
    renderTable();
    await tick('Draw from 202606-S0099');
    await tick('Draw from 202606-S0099');

    fireEvent.click(screen.getByRole('button', { name: /create spo/i }));

    await waitFor(() => expect(state.create).toHaveBeenCalledTimes(1));
    const [, lines] = state.create.mock.calls[0];
    expect(lines[0].qty).toBe(100);
    expect(lines[0].location_splits).toEqual([
      { warehouse_id: 'wh-1', qty: 70 },
      { warehouse_id: 'wh-2', qty: 30 },
    ]);
  });

  it('keeps a quantity the operator typed themselves, clamped to what is ticked', async () => {
    renderTable();
    await screen.findByTitle(/which po covers this/i);
    fireEvent.change(qtyInput(), { target: { value: '50' } });

    await tick('Draw from 202605-S0060');
    await tick('Draw from 202605-S0060');

    // Their 50 survives the round trip - it was a decision, not a derived default.
    expect(qtyInput()).toHaveValue(50);
  });
});

/**
 * Browser pass 3, finding 3 - the split has to SAY what no tick claims.
 *
 * Untick an order whose warehouse is also the suggested one and the arithmetic does not
 * move: 40 ticked + 30 unassigned at BRW reads exactly like 70 unassigned at BRW. The
 * quantity is right either way; what the screen never said is how much of it is nobody's.
 */
describe('F7 - unticking an SO line shows up as Unassigned', () => {
  beforeEach(() => {
    state.suggestion = suggestion({ lines: [plannerLine()] });
    state.create = vi.fn().mockResolvedValue({
      shipment_id: 'sh-1',
      shipment_number: 'ABCU1000001',
      created_spos: [],
      skipped: [],
      allocations: [],
      demand_links: [],
    });
  });

  it('states the unassigned share on the location cell', async () => {
    renderTable();
    await screen.findByTitle(/which demand this spo is for/i);

    // 40 + 30 ticked of 100: the other 30 is free stock at the suggested warehouse.
    expect(screen.getAllByText(/30 unassigned/).length).toBeGreaterThanOrEqual(1);
  });

  it('moves the unassigned share when a tick is dropped', async () => {
    renderTable();
    fireEvent.click(await screen.findByTitle(/which demand this spo is for/i));

    // SI26-0100 is at BRW, which is also the suggested warehouse - so the SPLIT is
    // unchanged and only the unassigned reading can tell the two apart.
    fireEvent.click(screen.getByRole('checkbox', { name: 'Cover SI26-0100' }));

    expect(await screen.findByText(/70 unassigned/)).toBeInTheDocument();
  });

  it('says nothing about unassigned when every piece is spoken for', async () => {
    state.suggestion = suggestion({
      lines: [plannerLine({ packed_qty: 70, po_covered_qty: 70, suggested_qty: 70 })],
    });
    renderTable();
    await screen.findByTitle(/which demand this spo is for/i);

    expect(screen.queryByText(/unassigned/)).not.toBeInTheDocument();
  });
});

/**
 * Browser pass 4, finding 2 - a typed quantity survives a round trip through the ticks.
 *
 * The recompute wrote the CLAMPED figure back into the quantity, so unticking the only
 * take stored 0 and the re-tick had nothing left to restore.
 */
describe('F7 - the quantity the operator typed is theirs', () => {
  const oneTake = () =>
    plannerLine({
      po_takes: [
        {
          po_line_id: 'pol-only',
          po_number: '202605-S0060',
          qty: 100,
          expected_date: '2026-09-01',
          po_date: '2026-05-02',
          supplier_name: 'Kailu',
          open_qty: 100,
        },
      ],
    });

  beforeEach(() => {
    state.suggestion = suggestion({ lines: [oneTake()] });
  });

  const qtyInput = () => screen.getByTitle(/what the TICKED POs pull this SPO up to/i);
  const toggle = async () => {
    fireEvent.click(await screen.findByTitle(/which po covers this/i));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Draw from 202605-S0060' }));
  };

  it('gives back the typed figure after untick and re-tick, every time', async () => {
    renderTable();
    await screen.findByTitle(/which po covers this/i);
    fireEvent.change(qtyInput(), { target: { value: '40' } });
    expect(qtyInput()).toHaveValue(40);

    await toggle();
    expect(qtyInput()).toHaveValue(0);
    await toggle();
    expect(qtyInput()).toHaveValue(40);

    // And again - the second round trip used to give back whatever the first one left.
    await toggle();
    expect(qtyInput()).toHaveValue(0);
    await toggle();
    expect(qtyInput()).toHaveValue(40);
  });

  it('never lets the typed figure exceed what is ticked', async () => {
    state.suggestion = suggestion({
      lines: [oneTake()],
    });
    renderTable();
    await screen.findByTitle(/which po covers this/i);
    fireEvent.change(qtyInput(), { target: { value: '90' } });

    await toggle();
    await toggle();

    expect(qtyInput()).toHaveValue(90);
  });
});

/**
 * R22 / AC-G4, AC-G5, AC-G6 - the destinations live in the EXPANDED ROW, not a popover.
 *
 * The chevron in the Location cell opens a full-width panel holding the destination rows,
 * the Unassigned remainder and Add location. What it does NOT hold is the coverage list:
 * which orders this SPO is for moved to the SO covered lightbox (captain, 27 Aug).
 */
describe('R22 - the destinations expand under the row', () => {
  beforeEach(() => {
    state.suggestion = suggestion({ lines: [plannerLine()] });
    state.create = vi.fn().mockResolvedValue({
      shipment_id: 'sh-1',
      shipment_number: 'ABCU1000001',
      created_spos: [],
      skipped: [],
      allocations: [],
      demand_links: [],
    });
  });

  /** The Location cell reads "2 locations" for the default split - and IS the chevron. */
  const chevron = async () => await screen.findByRole('button', { name: /BRW|locations/ });
  const qtyRow = (n: number) =>
    screen.getByRole('spinbutton', { name: `Quantity for destination ${n}` });

  it('opens the destination rows from the Location cell (AC-G4)', async () => {
    renderTable();

    const trigger = await chevron();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: /add location/i })).not.toBeInTheDocument();

    fireEvent.click(trigger);

    expect(await screen.findByText(/SRTWT7443 - destinations/)).toBeInTheDocument();
    // 40 to the project row's BRW plus the unassigned 30, and 30 to the retail row's MWH.
    expect(qtyRow(1)).toHaveValue(70);
    expect(qtyRow(2)).toHaveValue(30);
    expect(screen.getByRole('button', { name: /add location/i })).toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
  });

  it('carries no coverage list - that is the SO covered lightbox (AC-G4)', async () => {
    renderTable();
    fireEvent.click(await chevron());

    await screen.findByText(/SRTWT7443 - destinations/);
    expect(screen.queryByText(/What this covers/i)).not.toBeInTheDocument();
  });

  it('states the remainder as Unassigned, and turns destructive when the split exceeds the SPO qty', async () => {
    renderTable();
    fireEvent.click(await chevron());
    await screen.findByText(/SRTWT7443 - destinations/);

    // The default split adds up exactly, so nothing is left over.
    expect(screen.getByText('Unassigned').parentElement).not.toHaveClass('text-destructive');

    fireEvent.change(qtyRow(1), { target: { value: '200' } });

    const unassigned = screen.getByText('Unassigned').parentElement as HTMLElement;
    expect(unassigned).toHaveClass('text-destructive');
    expect(unassigned).toHaveTextContent('-130');
    expect(screen.getByText(/location split does not add up/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create spo/i })).toBeDisabled();
  });

  it('removing a destination leaves its quantity unassigned', async () => {
    renderTable();
    fireEvent.click(await chevron());
    await screen.findByText(/SRTWT7443 - destinations/);

    fireEvent.click(screen.getAllByRole('button', { name: 'Remove destination' })[1]);

    expect(qtyRow(1)).toHaveValue(70);
    expect(screen.queryByRole('spinbutton', { name: 'Quantity for destination 2' })).not.toBeInTheDocument();
    expect(screen.getByText('Unassigned').parentElement).toHaveTextContent('30');
  });

  it('Add location adds a row for what is left over, and it reaches the create', async () => {
    renderTable();
    fireEvent.click(await chevron());
    await screen.findByText(/SRTWT7443 - destinations/);
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove destination' })[1]);

    fireEvent.click(screen.getByRole('button', { name: /add location/i }));

    // The remaining 30 lands on the row that was just added, at the warehouse not already
    // used - so the split adds up again and Create SPO is allowed.
    expect(qtyRow(2)).toHaveValue(30);
    fireEvent.click(screen.getByRole('button', { name: /create spo/i }));
    await waitFor(() => expect(state.create).toHaveBeenCalledTimes(1));
    const [, lines] = state.create.mock.calls[0];
    expect(lines[0].location_splits).toEqual([
      { warehouse_id: 'wh-1', qty: 70 },
      { warehouse_id: 'wh-2', qty: 30 },
    ]);
  });

  it('Expand all opens every line and Collapse all closes them (AC-G5)', async () => {
    state.suggestion = suggestion({
      lines: [plannerLine(), plannerLine({ shipment_line_id: 'sl-2', item_code: 'SRTWT9000' })],
    });
    renderTable();
    await screen.findAllByRole('button', { name: /BRW|locations/ });

    fireEvent.click(screen.getByRole('button', { name: /expand all/i }));

    expect(await screen.findByText(/SRTWT7443 - destinations/)).toBeInTheDocument();
    expect(screen.getByText(/SRTWT9000 - destinations/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /collapse all/i }));

    await waitFor(() =>
      expect(screen.queryByText(/SRTWT7443 - destinations/)).not.toBeInTheDocument(),
    );
    expect(screen.queryByText(/SRTWT9000 - destinations/)).not.toBeInTheDocument();
  });

  it('Expand all opens only the lines that CAN be split', async () => {
    // `toggleAllRowsExpanded(true)` ignores `getRowCanExpand`, so it opened a row under every
    // covered line too, saying "No destination can be chosen for this line" - and that row's
    // own chevron is disabled, so nothing on screen could close it again.
    state.suggestion = suggestion({
      lines: [
        plannerLine(),
        plannerLine({
          shipment_line_id: 'sl-2',
          item_code: 'SRTWT9000',
          cannot_convert: true,
          reason: 'No PO to pull from - raise the PO in AutoCount first.',
          suggested_qty: 0,
          po_covered_qty: 0,
        }),
      ],
    });
    renderTable();

    fireEvent.click(await screen.findByRole('button', { name: /expand all/i }));

    expect(await screen.findByText(/SRTWT7443 - destinations/)).toBeInTheDocument();
    expect(
      screen.queryByText('No destination can be chosen for this line.'),
    ).not.toBeInTheDocument();
  });

  it('Expand all and Collapse all say why when no line can be split', async () => {
    state.suggestion = suggestion({
      lines: [
        plannerLine({
          cannot_convert: true,
          reason: 'No PO to pull from - raise the PO in AutoCount first.',
          suggested_qty: 0,
          po_covered_qty: 0,
        }),
      ],
    });
    renderTable();

    const expandAll = await screen.findByRole('button', { name: /expand all/i });
    const collapseAll = screen.getByRole('button', { name: /collapse all/i });
    expect(expandAll).toBeDisabled();
    expect(collapseAll).toBeDisabled();
    expect(expandAll).toHaveAttribute('title', 'No line can be split yet');
    expect(collapseAll).toHaveAttribute('title', 'No line can be split yet');
  });

  it('a line nothing can be sent for does not expand', async () => {
    state.suggestion = suggestion({
      lines: [
        plannerLine({
          cannot_convert: true,
          reason: 'No PO to pull from - raise the PO in AutoCount first.',
          suggested_qty: 0,
          po_covered_qty: 0,
        }),
      ],
    });
    renderTable();

    expect(await screen.findByText('No location')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'No location' })).not.toBeInTheDocument();
  });
});

/**
 * R21 / AC-G1, AC-G2, AC-G3, AC-G6 - the four figures open the SHARED lightbox.
 *
 * PO covers and SO covered carry the ticks that used to live in a popover; On hand and
 * Incoming SPO open the same bodies the loading plan and reorder planning already use. What
 * the popovers could not do is what these assert: a table wide enough to name documents, a
 * footer stating what the ticks add up to, and a surface that survives a tick.
 */
describe('R21 - the four figures open the shared lightbox', () => {
  beforeEach(() => {
    state.suggestion = suggestion({ lines: [plannerLine({ on_hand: 2, incoming_spo: 120 })] });
    state.create = vi.fn().mockResolvedValue({
      shipment_id: 'sh-1',
      shipment_number: 'ABCU1000001',
      created_spos: [],
      skipped: [],
      allocations: [],
      demand_links: [],
    });
  });

  const openFigure = async (title: RegExp) => {
    fireEvent.click(await screen.findByTitle(title));
    return screen.getByRole('dialog');
  };
  const PO = /which po covers this/i;
  const SO = /which demand this spo is for/i;
  const ON_HAND = /where this product is on hand/i;
  const INCOMING = /what is already on the water/i;

  it('PO covers opens a dialog listing every take, pre-ticked, with the covers footer (AC-G1)', async () => {
    renderTable();

    const dialog = await openFigure(PO);

    expect(within(dialog).getByText(/PO covers · SRTWT7443/)).toBeInTheDocument();
    expect(within(dialog).getByRole('checkbox', { name: 'Draw from 202605-S0060' })).toBeChecked();
    expect(within(dialog).getByRole('checkbox', { name: 'Draw from 202606-S0099' })).toBeChecked();
    expect(
      within(dialog).getByText('2 of 2 POs · covers 100 of packed 100'),
    ).toBeInTheDocument();
  });

  it('unticking in the dialog lowers the cell and clamps the SPO qty (AC-G1)', async () => {
    renderTable();
    const dialog = await openFigure(PO);

    // The 150-open line is the one that could cover the whole container; without it only
    // the 60-open line is left, and the SPO cannot be worth more than that.
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Draw from 202606-S0099' }));

    expect(screen.getByTitle(PO)).toHaveTextContent('60');
    expect(screen.getByText('1 of 2 POs')).toBeInTheDocument();
    expect(screen.getByTitle(/what the TICKED POs pull this SPO up to/i)).toHaveValue(60);
    // The dialog stays open across the tick - it is a lightbox, not a hover surface.
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('SO covered lists project first then retail, with the take per row and the unassigned footer (AC-G2, AC-G3)', async () => {
    renderTable();

    const dialog = await openFigure(SO);

    const rows = within(dialog).getAllByRole('row');
    expect(rows[1].textContent).toContain('SI26-0100');
    expect(rows[2].textContent).toContain('SO-2201');
    expect(rows[3].textContent).toContain('SO-2202');
    // Open / Take per row, off the one walk: 40 and 30 are served in full, and the order
    // nobody ticked gets nothing.
    expect(rows[1].querySelectorAll('td')[6].textContent).toBe('40');
    expect(rows[3].querySelectorAll('td')[5].textContent).toBe('90');
    expect(rows[3].querySelectorAll('td')[6].textContent).toBe('0');
    expect(within(dialog).getByText('Unassigned 30')).toBeInTheDocument();
  });

  it('ticking in the SO dialog re-walks the take without closing it (AC-G2)', async () => {
    renderTable();
    const dialog = await openFigure(SO);

    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Cover SI26-0100' }));

    // 30 to the retail line that is still ticked, and the other 70 claimed by nobody.
    expect(screen.getByTitle(SO)).toHaveTextContent('30');
    expect(within(screen.getByRole('dialog')).getByText('Unassigned 70')).toBeInTheDocument();
  });

  it('On hand opens the location dialog for this product, with the stock timestamp (AC-G3)', async () => {
    useLocationStock.mockReturnValue({
      data: {
        product_id: 'p-1',
        as_of: '2026-08-27T06:05:00',
        locations: [
          {
            warehouse_id: 'wh-1',
            warehouse_code: 'BRW',
            on_hand: 2,
            reserved: 0,
            held_by_decisions: 0,
            free: 2,
            so_qty: 60,
            spo_qty: 0,
            available: -58,
            is_pool: true,
          },
        ],
      },
      isLoading: false,
    });
    renderTable();

    const dialog = await openFigure(ON_HAND);

    expect(within(dialog).getByText(/On hand · SRTWT7443/)).toBeInTheDocument();
    expect(within(dialog).getByText('BRW')).toBeInTheDocument();
    expect(within(dialog).getByText(/Stock as of/)).toBeInTheDocument();
    expect(useLocationStock).toHaveBeenCalledWith('p-1', true);
  });

  it('Incoming SPO opens the SPO dialog for this supplier and product (AC-G3)', async () => {
    useContainerRequestDrill.mockReturnValue({
      data: {
        kind: 'spo',
        total: 120,
        rows: [
          {
            spo_number: 'CRM-SPO-0007',
            shipment_id: 'sh-9',
            shipment_number: 'FSCU8092210',
            warehouse_code: 'BRW',
            qty: 120,
            received: 0,
            eta: '2026-09-14',
            arrived_at: null,
            status: 'In transit',
          },
        ],
        history: [],
      },
      isLoading: false,
    });
    renderTable();

    const dialog = await openFigure(INCOMING);

    expect(within(dialog).getByText(/SPO · SRTWT7443/)).toBeInTheDocument();
    expect(within(dialog).getByText('CRM-SPO-0007')).toBeInTheDocument();
    expect(useContainerRequestDrill).toHaveBeenCalledWith('sup-1', 'p-1', 'spo');
  });

  it('says nothing is on its way when the drill comes back empty', async () => {
    renderTable();

    const dialog = await openFigure(INCOMING);

    expect(within(dialog).getByText(NO_SPO_TO_POOL)).toBeInTheDocument();
  });

  it('opens a dialog and no popover, and Escape closes it (AC-G6)', async () => {
    renderTable();

    const dialog = await openFigure(PO);
    expect(document.querySelector('[data-radix-popper-content-wrapper]')).toBeNull();

    fireEvent.keyDown(dialog, { key: 'Escape', code: 'Escape' });

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    // The figure is still there to be opened again.
    expect(screen.getByTitle(PO)).toBeInTheDocument();
  });

  it('a line with no supplier cannot drill the water, and reads as plain text', async () => {
    state.suggestion = suggestion({
      lines: [plannerLine({ supplier_id: null, supplier_name: null, incoming_spo: 5 })],
    });
    renderTable();

    await screen.findByTitle(PO);
    expect(screen.queryByTitle(INCOMING)).not.toBeInTheDocument();
  });
});
