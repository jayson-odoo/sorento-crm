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
import { fireEvent, render, screen } from '@testing-library/react';
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
    expect(screen.getByText(/moves this project to PO Received/i)).toBeInTheDocument();
  });

  it('says what recording the first PO will do', async () => {
    renderPos();

    expect(await screen.findByText(/No PO received yet/i)).toBeInTheDocument();
    expect(screen.getByText(/moves this project to PO Received/i)).toBeInTheDocument();
    expect(screen.getByText(/archived but not deleted/i)).toBeInTheDocument();
  });

  it('separates the two mismatch kinds instead of one generic warning', async () => {
    listPurchaseOrders.mockResolvedValue([
      po({ model_mismatch_count: 2, price_mismatch_count: 1 }),
    ]);

    renderPos();

    expect(await screen.findByText('2 not quoted')).toBeInTheDocument();
    expect(screen.getByText('1 price differs')).toBeInTheDocument();
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
    listPurchaseOrders.mockResolvedValue([po()]);
    listPurchaseOrderLines.mockResolvedValue([
      line({ unit_price: '820.00', quoted_unit_price: '900.00', price_mismatch: true }),
    ]);

    renderPos();

    // The ordered price is now an editable cell, so it reads as a value rather than as text.
    expect(
      await screen.findByRole('textbox', { name: 'Ordered at on SRT-WC-01' }),
    ).toHaveValue('820.00');
    expect(screen.getByText('Quoted RM 900.00')).toBeInTheDocument();
    expect(screen.getByText('Price differs')).toBeInTheDocument();
  });

  it('says plainly when a PO is bound to no version, rather than implying a clean check', async () => {
    listPurchaseOrders.mockResolvedValue([po({ quotation_version_id: null })]);
    listPurchaseOrderLines.mockResolvedValue([line()]);

    renderPos();

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

  it('offers no write affordance to a reader', async () => {
    listPurchaseOrders.mockResolvedValue([po()]);

    renderPos({ can_edit: false });

    expect(await screen.findByText('PO-9001')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Record a PO/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Delete PO-9001/i })).toBeNull();
  });
});

describe('SamplesPanel', () => {
  it('tells the user a sample needs a quoted version first', async () => {
    renderSamples();

    expect(await screen.findByText(/No samples sent yet/i)).toBeInTheDocument();
    expect(screen.getByText(/price a scope first/i)).toBeInTheDocument();
  });

  it('states that a version was superseded rather than leaving a badge off', async () => {
    listSamples.mockResolvedValue([sample({ is_version_current: false })]);

    renderSamples();

    expect(await screen.findByText('Version superseded')).toBeInTheDocument();
    expect(screen.getByText('1 against a superseded version')).toBeInTheDocument();
  });

  it('names the scope and version on every row', async () => {
    listSamples.mockResolvedValue([
      sample({ scope_label: 'Common Area', version_no: 3, submitted_by_name: 'Siti' }),
    ]);

    renderSamples();

    expect(await screen.findByText(/Common Area v3/)).toBeInTheDocument();
    expect(screen.getByText(/by Siti/)).toBeInTheDocument();
  });

  it('says feedback is missing instead of rendering an empty gap', async () => {
    listSamples.mockResolvedValue([sample({ developer_feedback: null })]);

    renderSamples();

    expect(await screen.findByText(/No feedback recorded yet/i)).toBeInTheDocument();
  });
});
