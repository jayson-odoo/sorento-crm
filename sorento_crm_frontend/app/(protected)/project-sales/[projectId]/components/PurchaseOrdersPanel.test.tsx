/**
 * S4 - PurchaseOrdersPanel + SamplesPanel (AC-F1, AC-F2, AC-F8, AC-F9, AC-F9a).
 *
 * The distinction worth pinning is the one AC-F9 and AC-F9a draw: a MISMATCH reads as an
 * exception to chase, while DRIFT from v1 reads as a plain number. A UI that presented
 * erosion as an alert would make every successfully negotiated PO look like a problem,
 * and the guardrail would be ignored within a week.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  Project,
  ProjectPurchaseOrder,
  ProjectSample,
  PurchaseOrderLine,
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

const listPurchaseOrders = vi.fn();
const listPurchaseOrderLines = vi.fn();
const listSamples = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  // Without this the grid never leaves its skeleton: the real hook fetches saved column
  // order and `isLoading` gates the body rows, and nothing answers that call under jsdom.
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listPurchaseOrders: (...args: unknown[]) => listPurchaseOrders(...args),
    listPurchaseOrderLines: (...args: unknown[]) => listPurchaseOrderLines(...args),
    listSamples: (...args: unknown[]) => listSamples(...args),
    listQuotations: vi.fn(async () => []),
    listQuotationVersions: vi.fn(async () => []),
    listParties: vi.fn(async () => ({ data: [], pagination: { total: 0 } })),
  };
});

import { PurchaseOrderLinesEditor } from './PurchaseOrderLinesEditor';
import { PurchaseOrdersPanel } from './PurchaseOrdersPanel';
import { SamplesPanel } from './SamplesPanel';

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

function po(overrides: Partial<ProjectPurchaseOrder> = {}): ProjectPurchaseOrder {
  return {
    id: 'po1',
    project_id: 'p1',
    po_source: 'contractor_direct',
    po_number: 'PO-9001',
    line_count: 1,
    line_total: '20000.00',
    model_mismatch_count: 0,
    price_mismatch_count: 0,
    ...overrides,
  };
}

function line(overrides: Partial<PurchaseOrderLine> = {}): PurchaseOrderLine {
  return {
    id: 'l1',
    po_id: 'po1',
    product_code: 'SRT-WC-01',
    unit_price: '900.00',
    quantity: '10.00',
    line_total: '9000.00',
    model_mismatch: false,
    price_mismatch: false,
    sort_order: 0,
    ...overrides,
  };
}

function sample(overrides: Partial<ProjectSample> = {}): ProjectSample {
  return {
    id: 's1',
    project_id: 'p1',
    quotation_version_id: 'v1',
    scope_label: 'House Units',
    version_no: 1,
    is_version_current: true,
    ...overrides,
  };
}

function renderPos(overrides: Partial<Project> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseOrdersPanel project={project(overrides)} />
    </QueryClientProvider>,
  );
}

/**
 * The lines live on the PO's own PAGE now, not under the list, so the component under test is
 * the editor itself. Rendering it through the panel was always indirect; it is now impossible.
 */
function renderLines(poOverrides: Partial<ProjectPurchaseOrder> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseOrderLinesEditor project={project()} po={po(poOverrides)} />
    </QueryClientProvider>,
  );
}

function renderSamples(overrides: Partial<Project> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SamplesPanel project={project(overrides)} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listPurchaseOrders.mockResolvedValue([]);
  listPurchaseOrderLines.mockResolvedValue([]);
  listSamples.mockResolvedValue([]);
});

describe('PurchaseOrdersPanel', () => {
  it('keeps the heading and the empty state, without the lesson under the heading', async () => {
    renderPos();

    // The client on the panel subtitles: "if we have to explain for the user to know how
    // to use, then we fail in user experience". The heading and the empty state stay -- an
    // empty section still has to say what would be here and offer the next step.
    expect(await screen.findByText(/No PO received yet/i)).toBeInTheDocument();
    expect(screen.getByText('Purchase orders')).toBeInTheDocument();
    expect(
      screen.queryByText(/checked against the version they were last shown/i),
    ).toBeNull();
    // The explainer under the heading is gone (ADR 1e); the two ways in live in the toolbar.
    expect(screen.getByRole('button', { name: /Upload a PO document/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Record a PO/i })).toBeInTheDocument();
  });

  it('offers both ways in when nothing is recorded, without explaining the funnel', async () => {
    renderPos();

    expect(await screen.findByText(/No PO received yet/i)).toBeInTheDocument();
    // The two ways in live in the TOOLBAR only (ADR 1d): no centred duplicates in the empty
    // state, and no paragraph teaching what recording a PO does to the funnel.
    expect(screen.getByRole('button', { name: /Upload a PO document/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Record a PO/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Record it by hand/i })).toBeNull();
    expect(screen.queryByText(/moves this project to PO Received/i)).not.toBeInTheDocument();
  });

  it('separates the two mismatch kinds instead of one generic warning', async () => {
    listPurchaseOrders.mockResolvedValue([
      po({ model_mismatch_count: 2, price_mismatch_count: 1 }),
    ]);

    renderPos();

    // Both counts share the one "To check" cell, and both are still NAMED rather than
    // collapsed into a single "3 problems": the two mean different work.
    expect(await screen.findByText(/2 not quoted.*1 price differs/)).toBeInTheDocument();
  });

  it('shows erosion from v1 as a number, not as an alert', async () => {
    listPurchaseOrders.mockResolvedValue([
      po({ v1_total: '10000.00', drift_delta: '-2000.00', drift_percent: '-20.00' }),
    ]);

    renderPos();

    expect(await screen.findByText(/20\.0% below v1 \(RM 10,000\.00\)/)).toBeInTheDocument();
    // Deliberately NOT presented as a problem: nothing here reads as a mismatch badge.
    expect(screen.queryByText(/price differs/i)).toBeNull();
  });

  it('puts the quoted price beside the ordered price on a flagged line', async () => {
    listPurchaseOrderLines.mockResolvedValue([
      line({ unit_price: '820.00', quoted_unit_price: '900.00', price_mismatch: true }),
    ]);

    renderLines();

    // A READ by default now (the edit view owns the inputs), so the ordered price reads as
    // money with what was quoted underneath it.
    expect(await screen.findByText('RM 820.00')).toBeInTheDocument();
    expect(screen.getByText('Quoted RM 900.00')).toBeInTheDocument();
    expect(screen.getByText('Price differs')).toBeInTheDocument();
  });

  it('says plainly when a PO is bound to no version, rather than implying a clean check', async () => {
    listPurchaseOrderLines.mockResolvedValue([line()]);

    renderLines({ quotation_version_id: null });

    expect(
      await screen.findByText(/not tied to a quotation version/i),
    ).toBeInTheDocument();
  });

  it('warns that deleting a PO leaves the funnel where it is', async () => {
    listPurchaseOrders.mockResolvedValue([po({ line_count: 3 })]);

    renderPos();

    fireEvent.click(await screen.findByRole('button', { name: /Delete PO-9001/i }));

    expect(await screen.findByText(/stays at PO Received/i)).toBeInTheDocument();
  });

  it('totals the value inside the table, under the column it sums', async () => {
    listPurchaseOrders.mockResolvedValue([
      po({ id: 'po1', po_number: 'PO-9001', line_total: '20000.00' }),
      po({ id: 'po2', po_number: 'PO-9002', line_total: '5000.50' }),
    ]);

    const { container } = renderPos();

    await screen.findByText('PO-9001');

    // In the table's own <tfoot>, not a strip beside the toolbar: a total nobody can align
    // with a column is a number without a unit.
    const footer = container.querySelector('tfoot');
    expect(footer).not.toBeNull();
    expect(within(footer as HTMLElement).getByText('RM 25,000.50')).toBeInTheDocument();
    expect(within(footer as HTMLElement).getByText('Total')).toBeInTheDocument();

    // The footer cell sits at the same column index as the Value header, which is what makes
    // it read as a sum rather than as a stray figure.
    const headers = [...container.querySelectorAll('thead th')].map((th) => th.textContent);
    const valueIndex = headers.findIndex((text) => text?.includes('Value'));
    const footerCells = [...(footer as HTMLElement).querySelectorAll('td')];
    expect(footerCells[valueIndex]?.textContent).toBe('RM 25,000.50');
  });

  it('counts the rows through the standard pagination bar, not a sentence', async () => {
    listPurchaseOrders.mockResolvedValue([po()]);

    renderPos();

    // "1 PO on this project" told the user what "1 - 1 of 1" already tells them, in a place
    // the rest of the system does not use.
    expect(await screen.findByText(/1 - 1 of 1/)).toBeInTheDocument();
    expect(screen.getByText(/Rows per page/i)).toBeInTheDocument();
    expect(screen.queryByText(/on this project/i)).toBeNull();
  });

  it('offers no write affordance to a reader', async () => {
    listPurchaseOrders.mockResolvedValue([po()]);

    renderPos({ can_edit: false });

    expect((await screen.findAllByText('PO-9001')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /Record a PO/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Delete PO-9001/i })).toBeNull();
  });
});

describe('SamplesPanel', () => {
  it('tells the user a sample needs a quoted version first', async () => {
    renderSamples();

    expect(await screen.findByText(/No samples sent yet/i)).toBeInTheDocument();
    // The heading says it; the sentence explaining the dependency is gone.
    expect(screen.getByText('No samples sent yet')).toBeInTheDocument();
  });

  it('states that a version was superseded rather than leaving a badge off', async () => {
    listSamples.mockResolvedValue([sample({ is_version_current: false })]);

    renderSamples();

    expect(await screen.findByText('Superseded')).toBeInTheDocument();
    expect(screen.getByText('1 against a superseded version')).toBeInTheDocument();
  });

  it('names the scope and version on every row', async () => {
    listSamples.mockResolvedValue([
      sample({ scope_label: 'Common Area', version_no: 3, submitted_by_name: 'Siti' }),
    ]);

    renderSamples();

    expect(await screen.findByText('Common Area')).toBeInTheDocument();
    // Scope and version are separate columns now, so they are asserted separately.
    expect(screen.getByText('v3')).toBeInTheDocument();
    // Its own "By" column now, so the name stands alone without the "by" preposition.
    expect(screen.getByText('Siti')).toBeInTheDocument();
  });

  it('says feedback is missing instead of rendering an empty gap', async () => {
    listSamples.mockResolvedValue([sample({ developer_feedback: null })]);

    renderSamples();

    expect((await screen.findAllByText('-')).length).toBeGreaterThan(0);
  });
});
