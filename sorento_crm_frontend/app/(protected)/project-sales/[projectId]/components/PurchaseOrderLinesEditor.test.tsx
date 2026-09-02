/**
 * PO lines, entered like a spreadsheet (AC-F9), inside an edit VIEW.
 *
 * The columns are this screen's own; the spreadsheet behaviour behind them is pinned once,
 * in InlineLineTable.test.tsx. What is pinned HERE is that the columns are the fields the
 * dialog used to collect, that a READ is a read (no inputs, no add row, nothing that can be
 * saved by moving the caret), and that in a session every change is STAGED - no request leaves
 * the browser until the page's own Save sends the whole set.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  Project,
  ProjectPurchaseOrder,
  PurchaseOrderLine,
  StagedPurchaseOrderLine,
} from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listPurchaseOrderLines = vi.fn();
const createPurchaseOrderLine = vi.fn();
const updatePurchaseOrderLine = vi.fn();
const deletePurchaseOrderLine = vi.fn();
const updatePurchaseOrder = vi.fn();

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listPurchaseOrderLines: (...args: unknown[]) => listPurchaseOrderLines(...args),
    createPurchaseOrderLine: (...args: unknown[]) => createPurchaseOrderLine(...args),
    updatePurchaseOrderLine: (...args: unknown[]) => updatePurchaseOrderLine(...args),
    deletePurchaseOrderLine: (...args: unknown[]) => deletePurchaseOrderLine(...args),
    updatePurchaseOrder: (...args: unknown[]) => updatePurchaseOrder(...args),
  };
});

// The product picker hits the shared products `/select` endpoint when it opens.
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: vi.fn(async () => []),
}));

vi.mock('@/lib/toast', () => ({
  toast: { custom: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

import {
  PurchaseOrderLinesEditor,
  stagedPoLinesToBody,
  stagedPoLinesTotal,
  unfinishedStagedPoLines,
} from './PurchaseOrderLinesEditor';
import { usePurchaseOrderEditSession } from '../pos/[poId]/components/usePurchaseOrderEditSession';

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Test',
    outcome: 'open',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    ...overrides,
  };
}

const PO: ProjectPurchaseOrder = {
  id: 'po1',
  project_id: 'p1',
  po_number: 'PO-9001',
  po_source: 'contractor_direct',
  quotation_version_id: 'v2',
  line_count: 1,
  line_total: '9000.00',
  model_mismatch_count: 0,
  price_mismatch_count: 0,
};

function line(overrides: Partial<PurchaseOrderLine> = {}): PurchaseOrderLine {
  return {
    id: 'pl1',
    po_id: 'po1',
    product_code: 'SRT-WC-01',
    description: 'Wall-hung WC',
    unit_price: '900.00',
    quantity: '10.00',
    uom: 'PCS',
    line_total: '9000.00',
    model_mismatch: false,
    price_mismatch: false,
    sort_order: 0,
    ...overrides,
  };
}

function staged(overrides: Partial<StagedPurchaseOrderLine> = {}): StagedPurchaseOrderLine {
  return {
    id: 'pl1',
    key: 'pl1',
    line: line(),
    draft: {
      product_id: '',
      product_code: 'SRT-WC-01',
      description: 'Wall-hung WC',
      quantity: '10.00',
      uom: 'PCS',
      unit_price: '900.00',
      notes: '',
    },
    removed: false,
    ...overrides,
  };
}

function renderRead(overrides: Partial<Project> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseOrderLinesEditor project={project(overrides)} po={PO} />
    </QueryClientProvider>,
  );
}

/**
 * The editor as the PO's page mounts it in a session: the REAL session hook, so what these
 * tests exercise is the seed / stage / stage-a-removal contract the page relies on rather than
 * a stand-in for it. `session` is handed back so a test can read what would be saved.
 */
function renderEditing(overrides: Partial<Project> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const session: { current: ReturnType<typeof usePurchaseOrderEditSession> | null } = {
    current: null,
  };

  function Harness() {
    const edit = usePurchaseOrderEditSession();
    session.current = edit;
    React.useEffect(() => {
      edit.begin();
      // Opened once, on mount, the way arriving with ?edit=1 does.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <PurchaseOrderLinesEditor
        project={project(overrides)}
        po={PO}
        edit={
          edit.isEditing
            ? {
                staged: edit.staged,
                seed: edit.seed,
                stage: edit.stage,
                toggleRemoved: edit.toggleRemoved,
              }
            : null
        }
      />
    );
  }

  const utils = render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  return { ...utils, session };
}

beforeEach(() => {
  vi.clearAllMocks();
  listPurchaseOrderLines.mockResolvedValue([line()]);
});

describe('PurchaseOrderLinesEditor as a read', () => {
  it('lays every field of a PO line out as a column', async () => {
    renderRead();

    for (const header of [
      'Our product',
      'Code on the PO',
      'Description',
      'Qty',
      'UOM',
      'Ordered at',
      'Total',
    ]) {
      expect(await screen.findByRole('columnheader', { name: header })).toBeInTheDocument();
    }
  });

  it('offers nothing to type into and nothing to save', async () => {
    renderRead();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    // A read line still reads as money, not as the raw string the API holds.
    expect(screen.getByText('RM 900.00')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a line' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Remove/ })).toBeNull();
  });

  it('keeps its header and points at Edit when the PO has no lines yet', async () => {
    listPurchaseOrderLines.mockResolvedValue([]);

    renderRead();

    expect(
      await screen.findByRole('columnheader', { name: 'Code on the PO' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Press Edit to enter what the PO ordered/i)).toBeInTheDocument();
  });

  it('says a reader cannot enter lines at all, rather than telling them to press Edit', async () => {
    listPurchaseOrderLines.mockResolvedValue([]);

    renderRead({ can_edit: false });

    expect(
      await screen.findByText(/recorded as a single amount with no line detail/i),
    ).toBeInTheDocument();
  });

  it('puts the quoted price beside the ordered price on a flagged line', async () => {
    listPurchaseOrderLines.mockResolvedValue([
      line({ unit_price: '820.00', quoted_unit_price: '900.00', price_mismatch: true }),
    ]);

    renderRead();

    expect(await screen.findByText('Quoted RM 900.00')).toBeInTheDocument();
    expect(screen.getByText('Price differs')).toBeInTheDocument();
  });

  it('totals the lines under the column it sums', async () => {
    listPurchaseOrderLines.mockResolvedValue([
      line({ id: 'pl1', line_total: '9000.00' }),
      line({
        id: 'pl2',
        product_code: 'SRT-BASIN',
        description: 'Counter-top basin',
        unit_price: '300.00',
        quantity: '2.00',
      }),
    ]);

    const { container } = renderRead();

    await screen.findByText('Wall-hung WC');
    const footer = container.querySelector('tfoot');
    expect(footer).not.toBeNull();
    expect(within(footer as HTMLElement).getByText('RM 9,600.00')).toBeInTheDocument();
  });

  it('says plainly when a PO is bound to no version, rather than implying a clean check', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <PurchaseOrderLinesEditor
          project={project()}
          po={{ ...PO, quotation_version_id: null }}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/not tied to a quotation version/i)).toBeInTheDocument();
  });
});

describe('PurchaseOrderLinesEditor in a session', () => {
  it('turns every cell into an input, in place', async () => {
    renderEditing();

    expect(
      await screen.findByRole('textbox', { name: 'Code on the PO on SRT-WC-01' }),
    ).toHaveValue('SRT-WC-01');
    expect(screen.getByRole('textbox', { name: 'Ordered at on SRT-WC-01' })).toHaveValue(
      '900.00',
    );
    expect(screen.getByRole('button', { name: 'Add a line' })).toBeInTheDocument();
  });

  it('moves the row total and the footer while a quantity is typed, and writes nothing', async () => {
    const { container } = renderEditing();

    fireEvent.change(await screen.findByRole('textbox', { name: 'Qty on SRT-WC-01' }), {
      target: { value: '3' },
    });

    // Twice: the row's own Total cell, and the footer that sums the column.
    expect(screen.getAllByText('RM 2,700.00')).toHaveLength(2);
    const footer = container.querySelector('tfoot');
    expect(within(footer as HTMLElement).getByText('RM 2,700.00')).toBeInTheDocument();
    expect(updatePurchaseOrderLine).not.toHaveBeenCalled();
    expect(updatePurchaseOrder).not.toHaveBeenCalled();
  });

  it('stages an edit onto the session instead of saving the row', async () => {
    const { session } = renderEditing();

    fireEvent.change(
      await screen.findByRole('textbox', { name: 'Ordered at on SRT-WC-01' }),
      { target: { value: '820.00' } },
    );

    await waitFor(() => expect(session.current?.linesChanged).toBe(true));
    expect(stagedPoLinesToBody(session.current?.staged ?? [])).toEqual([
      {
        id: 'pl1',
        product_id: null,
        product_code: 'SRT-WC-01',
        description: 'Wall-hung WC',
        unit_price: '820.00',
        quantity: '10.00',
        uom: 'PCS',
        notes: null,
      },
    ]);
    // There is no per-row tick in a session: the page's Save is the only commit point.
    expect(screen.queryByRole('button', { name: 'Save SRT-WC-01' })).toBeNull();
    expect(updatePurchaseOrderLine).not.toHaveBeenCalled();
  });

  it('adds a line as a row with no id, so the save reads it as new', async () => {
    const { session } = renderEditing();

    fireEvent.click(await screen.findByRole('button', { name: 'Add a line' }));
    fireEvent.change(
      await screen.findByRole('textbox', { name: 'Code on the PO on line 2' }),
      { target: { value: 'THEIRS-7' } },
    );
    fireEvent.change(screen.getByRole('textbox', { name: 'Ordered at on line 2' }), {
      target: { value: '410.00' },
    });

    await waitFor(() => expect(session.current?.staged).toHaveLength(2));
    expect(stagedPoLinesToBody(session.current?.staged ?? [])[1]).toEqual({
      product_id: null,
      product_code: 'THEIRS-7',
      description: null,
      unit_price: '410.00',
      quantity: '1',
      uom: null,
      notes: null,
    });
    expect(createPurchaseOrderLine).not.toHaveBeenCalled();
  });

  it('marks the cell that stops an unmatched line from being saved, live', async () => {
    const { session } = renderEditing();

    fireEvent.click(await screen.findByRole('button', { name: 'Add a line' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Description on line 2' }), {
      target: { value: 'Something they wrote' },
    });

    expect(await screen.findByText('Needed when no product is matched')).toBeInTheDocument();
    await waitFor(() => expect(session.current?.staged).toHaveLength(2));
    expect(unfinishedStagedPoLines(session.current?.staged ?? [])).toBe(1);
  });

  it('stages a removal without asking, keeps the row visible, and can take it back', async () => {
    const { session } = renderEditing();

    fireEvent.click(await screen.findByRole('button', { name: 'Remove SRT-WC-01' }));

    // Nothing destroyed, so nothing confirmed: the row stays on screen, struck through.
    expect(await screen.findByText('Removed on save')).toBeInTheDocument();
    expect(deletePurchaseOrderLine).not.toHaveBeenCalled();
    expect(screen.queryByText(/This action cannot be undone/i)).toBeNull();
    await waitFor(() => expect(session.current?.removedCount).toBe(1));
    // Out of the body, which is exactly how the endpoint deletes it.
    expect(stagedPoLinesToBody(session.current?.staged ?? [])).toEqual([]);

    fireEvent.click(screen.getByRole('button', { name: 'Restore SRT-WC-01' }));
    await waitFor(() => expect(session.current?.removedCount).toBe(0));
  });
});

describe('what the page saves', () => {
  it('leaves a removed line out of the body and sends no sort_order', () => {
    const body = stagedPoLinesToBody([
      staged(),
      staged({ id: 'pl2', key: 'pl2', removed: true }),
      staged({ id: null, key: 'new:1', line: null }),
    ]);

    expect(body).toHaveLength(2);
    expect(body[0].id).toBe('pl1');
    expect(body[1].id).toBeUndefined();
    expect(body.every((item) => !('sort_order' in item))).toBe(true);
  });

  it('totals only the lines that will still be there', () => {
    expect(
      stagedPoLinesTotal([staged(), staged({ id: 'pl2', key: 'pl2', removed: true })]),
    ).toBe('9000.00');
  });
});
