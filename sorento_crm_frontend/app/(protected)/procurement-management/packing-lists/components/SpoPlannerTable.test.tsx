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
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

vi.mock('@/app/(protected)/scm/services/fulfilmentService', () => ({
  getSpoSuggestion: (...args: unknown[]) => state.suggestionFn(...args),
  createSpo: (...args: unknown[]) => state.create(...args),
  deleteSpo: (...args: unknown[]) => state.deleteSpo(...args),
  downloadSpoWorksheet: (...args: unknown[]) => state.worksheet(...args),
}));

import { toast } from 'sonner';
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

    // 100 packed, 40 + 30 ticked - the remaining 30 is free stock.
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

    expect(await screen.findByText(/SO-2202/)).toBeInTheDocument();
    expect(screen.getByText(/nothing left for it/)).toBeInTheDocument();
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
