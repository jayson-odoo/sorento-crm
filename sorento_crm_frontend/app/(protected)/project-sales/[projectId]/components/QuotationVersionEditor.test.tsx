/**
 * S3 - QuotationVersionEditor (AC-E2, AC-E3, AC-E4, AC-E7).
 *
 * The rule being pinned is that editability comes from the SERVER's `is_current`, never
 * from a local guess such as "the highest number I can see". A superseded version is a
 * document the customer already holds, so it renders read-only WITH the reason, not
 * merely with its buttons missing.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  Project,
  ProjectQuotation,
  QuotationLine,
  QuotationVersion,
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

const listQuotationVersions = vi.fn();
const listQuotationLines = vi.fn();
const reviseQuotation = vi.fn();
const createQuotationLine = vi.fn();
const updateQuotationLine = vi.fn();

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    listQuotationVersions: (...args: unknown[]) => listQuotationVersions(...args),
    listQuotationLines: (...args: unknown[]) => listQuotationLines(...args),
    reviseQuotation: (...args: unknown[]) => reviseQuotation(...args),
    createQuotationLine: (...args: unknown[]) => createQuotationLine(...args),
    updateQuotationLine: (...args: unknown[]) => updateQuotationLine(...args),
  };
});

// The product picker hits the shared products `/select` endpoint when it opens. These tests
// do not exercise the dropdown, so the fetch is stubbed rather than the component replaced.
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: vi.fn(async () => []),
}));

import { QuotationVersionEditor } from './QuotationVersionEditor';

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

const QUOTATION: ProjectQuotation = {
  id: 'q1',
  project_id: 'p1',
  scope_label: 'House Units',
  outcome: 'open',
  version_count: 2,
  current_version_id: 'v2',
  current_version_no: 2,
  current_total: '9000.00',
  below_floor_count: 1,
  non_standard_count: 0,
  line_count: 1,
};

function version(overrides: Partial<QuotationVersion>): QuotationVersion {
  return {
    id: 'v1',
    quotation_id: 'q1',
    version_no: 1,
    is_current: false,
    total_amount: '0.00',
    ...overrides,
  };
}

function line(overrides: Partial<QuotationLine> = {}): QuotationLine {
  return {
    id: 'l1',
    version_id: 'v2',
    product_code: 'SRT-WC-01',
    description: 'Wall-hung WC',
    unit_price: '900.00',
    quantity: '10.00',
    line_total: '9000.00',
    is_non_standard: false,
    is_below_floor: false,
    sort_order: 0,
    ...overrides,
  };
}

const VERSIONS = [
  version({ id: 'v1', version_no: 1, frozen_at: '2026-07-01T02:00:00', total_amount: '8000.00' }),
  version({ id: 'v2', version_no: 2, is_current: true, total_amount: '9000.00' }),
];

function renderEditor(overrides: Partial<Project> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationVersionEditor project={project(overrides)} quotation={QUOTATION} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listQuotationVersions.mockResolvedValue(VERSIONS);
  listQuotationLines.mockResolvedValue([line()]);
  reviseQuotation.mockResolvedValue(version({ id: 'v3', version_no: 3, is_current: true }));
  createQuotationLine.mockResolvedValue(line({ id: 'l2' }));
  updateQuotationLine.mockResolvedValue(line());
});

describe('QuotationVersionEditor', () => {
  it('lands on the current version and marks the older one frozen', async () => {
    renderEditor();

    expect(await screen.findByRole('button', { name: 'v2' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'v1 (frozen)' })).toBeInTheDocument();
    // Lines are asked for on v2, not v1: current is the server's answer, not the first row.
    expect(listQuotationLines).toHaveBeenCalledWith('v2');
  });

  it('lets the current version be edited in place, without a dialog', async () => {
    renderEditor();

    expect(await screen.findByRole('button', { name: /Add a line/i })).toBeInTheDocument();
    // The line IS the row: every field is a cell, so there is nothing to open.
    expect(screen.getByRole('textbox', { name: 'Description on SRT-WC-01' })).toHaveValue(
      'Wall-hung WC',
    );
    expect(screen.getByRole('textbox', { name: 'Qty on SRT-WC-01' })).toHaveValue('10.00');
    expect(screen.queryByRole('button', { name: /Edit SRT-WC-01/i })).toBeNull();
  });

  it('turns a superseded version read-only and says where to edit instead', async () => {
    renderEditor();

    fireEvent.click(await screen.findByRole('button', { name: 'v1 (frozen)' }));

    // One line, not a paragraph on why versions freeze: the consequence is the useful part.
    expect(await screen.findByText(/Frozen\. Make changes on v2\./i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add a line/i })).toBeNull();
    expect(screen.queryByRole('textbox', { name: 'Qty on SRT-WC-01' })).toBeNull();
    // Frozen lines still read as money and quantities, not as raw API strings.
    expect(screen.getByText('RM 900.00')).toBeInTheDocument();
  });

  it('says what a revise will freeze before doing it', async () => {
    renderEditor();

    fireEvent.click(await screen.findByRole('button', { name: /Revise to v3/i }));

    expect(await screen.findByText(/frozen for good/i)).toBeInTheDocument();
    expect(screen.getByText(/its 1 line is/i)).toBeInTheDocument();
    expect(reviseQuotation).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Freeze v2 and continue/i }));
    await waitFor(() => expect(reviseQuotation).toHaveBeenCalledWith('q1'));
  });

  it('names the rule behind a below-floor line rather than just flagging it', async () => {
    listQuotationLines.mockResolvedValue([
      line({
        unit_price: '400.00',
        list_price: '1000.00',
        is_below_floor: true,
        floor_value_applied: '700.00',
        floor_level_applied: 'category_ancestor',
      }),
    ]);

    renderEditor();

    expect(await screen.findByText('Below floor')).toBeInTheDocument();
    expect(
      screen.getByText(/Floor was RM 700\.00, set on a parent category/),
    ).toBeInTheDocument();
    expect(screen.getByText('List RM 1,000.00')).toBeInTheDocument();
  });

  it('marks an off-catalog line as such, since it can never be standard', async () => {
    listQuotationLines.mockResolvedValue([
      line({
        product_code: null,
        product_id: null,
        description: 'Bespoke vanity top',
        is_non_standard: true,
      }),
    ]);

    renderEditor();

    expect(await screen.findByText('Off-catalog')).toBeInTheDocument();
    expect(screen.getByText('Non-standard')).toBeInTheDocument();
  });

  it('lays every field of a line out as a column', async () => {
    renderEditor();

    for (const header of ['Product', 'Description', 'Qty', 'UOM', 'Unit price', 'Counts per', 'Total']) {
      expect(await screen.findByRole('columnheader', { name: header })).toBeInTheDocument();
    }
    // Notes is a paragraph, so it keeps a home off the row rather than a six-character cell.
    expect(screen.getByRole('button', { name: 'Notes on SRT-WC-01' })).toBeInTheDocument();
  });

  it('moves the line total while the quantity is typed, before anything is saved', async () => {
    renderEditor();

    const qty = await screen.findByRole('textbox', { name: 'Qty on SRT-WC-01' });
    fireEvent.change(qty, { target: { value: '3' } });

    expect(screen.getByText('RM 2,700.00')).toBeInTheDocument();
    expect(updateQuotationLine).not.toHaveBeenCalled();
  });

  it('saves an edited line with the body the dialog used to send', async () => {
    renderEditor();

    const qty = await screen.findByRole('textbox', { name: 'Qty on SRT-WC-01' });
    fireEvent.change(qty, { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save SRT-WC-01' }));

    await waitFor(() => expect(updateQuotationLine).toHaveBeenCalledTimes(1));
    expect(updateQuotationLine).toHaveBeenCalledWith('v2', 'l1', {
      product_id: null,
      description_snapshot: 'Wall-hung WC',
      unit_price: '900.00',
      quantity: '12',
      uom: null,
      unit_type: null,
      notes: null,
    });
  });

  it('creates an added line with the body the dialog used to send', async () => {
    renderEditor();

    fireEvent.click(await screen.findByRole('button', { name: 'Add a line' }));
    const description = await screen.findByRole('textbox', {
      name: 'Description on line 2',
    });
    fireEvent.change(description, { target: { value: 'Bespoke vanity top' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Unit price on line 2' }), {
      target: { value: '1250.00' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save line 2' }));

    await waitFor(() => expect(createQuotationLine).toHaveBeenCalledTimes(1));
    expect(createQuotationLine).toHaveBeenCalledWith('v2', {
      product_id: null,
      description_snapshot: 'Bespoke vanity top',
      unit_price: '1250.00',
      quantity: '1',
      uom: null,
      unit_type: null,
      notes: null,
      // The line goes after the one already there, as the dialog placed it.
      sort_order: 10,
    });
  });

  it('marks the cell that stops an off-catalog line from being saved', async () => {
    renderEditor();

    fireEvent.click(await screen.findByRole('button', { name: 'Add a line' }));
    const description = await screen.findByRole('textbox', {
      name: 'Description on line 2',
    });
    // Typed into, so it is real data rather than a mis-click, but it has neither a product
    // nor a description to stand in for one.
    fireEvent.change(screen.getByRole('textbox', { name: 'Qty on line 2' }), {
      target: { value: '4' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save line 2' }));

    expect(await screen.findByText('Needed on an off-catalog line')).toBeInTheDocument();
    expect(description).toHaveAttribute('aria-invalid', 'true');
    expect(createQuotationLine).not.toHaveBeenCalled();
  });

  it('offers no write affordance to a reader', async () => {
    renderEditor({ can_edit: false });

    expect(await screen.findByRole('button', { name: 'v2' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Revise/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Add a line/i })).toBeNull();
  });
});
