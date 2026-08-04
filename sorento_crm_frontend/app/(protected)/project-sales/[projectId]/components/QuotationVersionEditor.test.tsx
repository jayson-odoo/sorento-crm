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

  it('lays every field of a line out as a column, in the printed order', async () => {
    renderEditor();

    // The order matters: the row is filled in reading left to right the way the customer
    // reads the printed quotation back.
    const printed = [
      'Item',
      'Product',
      'Description',
      'Tech spec',
      'Brand',
      'Qty',
      'UOM',
      'Unit price',
      'Complete set',
      'Counts per',
      'Rate only',
      'Total',
    ];
    for (const header of printed) {
      expect(await screen.findByRole('columnheader', { name: header })).toBeInTheDocument();
    }
    expect(
      screen.getAllByRole('columnheader').map((cell) => cell.textContent?.trim()),
    ).toEqual([...printed, 'Row actions']);
    // Notes is a paragraph, so it keeps a home off the row rather than a six-character cell.
    expect(screen.getByRole('button', { name: 'Notes on SRT-WC-01' })).toBeInTheDocument();
  });

  it('holds the printed columns as cells, and sends every one of them back', async () => {
    listQuotationLines.mockResolvedValue([
      line({
        item_label: 'A',
        brand: 'SORENTO',
        technical_spec: 'Rimless, 4/2.6L dual flush',
        complete_set: 'c/w seat cover',
      }),
    ]);

    renderEditor();

    // What the server sent is on screen, under the name the RESPONSE uses for it.
    expect(await screen.findByRole('textbox', { name: 'Item on SRT-WC-01' })).toHaveValue('A');
    expect(screen.getByRole('textbox', { name: 'Brand on SRT-WC-01' })).toHaveValue('SORENTO');
    expect(screen.getByRole('textbox', { name: 'Tech spec on SRT-WC-01' })).toHaveValue(
      'Rimless, 4/2.6L dual flush',
    );
    expect(screen.getByRole('textbox', { name: 'Complete set on SRT-WC-01' })).toHaveValue(
      'c/w seat cover',
    );

    fireEvent.change(screen.getByRole('textbox', { name: 'Brand on SRT-WC-01' }), {
      target: { value: 'MOCHA' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save SRT-WC-01' }));

    await waitFor(() => expect(updateQuotationLine).toHaveBeenCalledTimes(1));
    // The REQUEST calls the brand `brand_snapshot` while the response calls it `brand`. The
    // asymmetry is the API's, and the editor honours it rather than sending its own name.
    expect(updateQuotationLine.mock.calls[0][2]).toMatchObject({
      item_label: 'A',
      brand_snapshot: 'MOCHA',
      technical_spec: 'Rimless, 4/2.6L dual flush',
      complete_set: 'c/w seat cover',
    });
  });

  it('prints the words on a rate-only line, and leaves it out of the footer sum', async () => {
    listQuotationLines.mockResolvedValue([
      line(),
      line({
        id: 'l2',
        product_code: 'SRT-BIDET-09',
        unit_price: '500.00',
        quantity: '1.00',
        // Stored and printed, because the customer IS being shown a rate. It just does not
        // count: adding the sample's five alternates would have overstated it by RM 235,000.
        line_total: '500.00',
        is_rate_only: true,
      }),
    ]);

    renderEditor();

    expect(await screen.findByText('rate only')).toBeInTheDocument();
    // Never RM 0.00, which reads as free, and never blank, which reads as a fault.
    expect(screen.queryByText('RM 0.00')).toBeNull();
    expect(screen.queryByText('RM 500.00')).toBeNull();
    // The footer under the money column is the other line alone, not RM 9,500.00.
    const footer = screen.getByRole('table').querySelector('tfoot');
    expect(footer?.textContent).toContain('RM 9,000.00');
    expect(footer?.textContent).not.toContain('9,500');
    expect(
      screen.getByRole('checkbox', { name: 'Rate only on SRT-BIDET-09' }),
    ).toBeChecked();
  });

  it('marks a line rate-only from its own row, and says so in the total column', async () => {
    renderEditor();

    const toggle = await screen.findByRole('checkbox', { name: 'Rate only on SRT-WC-01' });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);

    // The total column answers immediately, off the draft, before anything is saved.
    expect(screen.getByText('rate only')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Save SRT-WC-01' }));
    await waitFor(() => expect(updateQuotationLine).toHaveBeenCalledTimes(1));
    expect(updateQuotationLine.mock.calls[0][2]).toMatchObject({ is_rate_only: true });
  });

  it('opens a section with one heading above the line that carries it', async () => {
    listQuotationLines.mockResolvedValue([
      line({ band_label: 'BILL NO 3 PAGE 15/4' }),
      line({ id: 'l2', product_code: 'SRT-BIDET-09', sort_order: 10 }),
    ]);

    renderEditor();

    const heading = await screen.findByRole('textbox', {
      name: 'Section heading on SRT-WC-01',
    });
    expect(heading).toHaveValue('BILL NO 3 PAGE 15/4');
    // ONCE, and only for the line that carries it: the line below is inside the section, it
    // does not repeat the heading.
    expect(screen.getAllByDisplayValue('BILL NO 3 PAGE 15/4')).toHaveLength(1);
    expect(
      screen.queryByRole('textbox', { name: 'Section heading on SRT-BIDET-09' }),
    ).toBeNull();

    // Directly above its own line, inside the same table, so the two cannot drift apart.
    const bandRow = heading.closest('tr');
    const lineRow = screen.getByRole('textbox', { name: 'Qty on SRT-WC-01' }).closest('tr');
    expect(bandRow?.nextElementSibling).toBe(lineRow);
  });

  it('starts a band on a line that had none', async () => {
    renderEditor();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Section heading on SRT-WC-01' }),
    );
    const heading = await screen.findByRole('textbox', {
      name: 'Section heading on SRT-WC-01',
    });
    fireEvent.change(heading, { target: { value: 'OPTIONAL ITEMS FOR OKU TOILET' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save SRT-WC-01' }));

    await waitFor(() => expect(updateQuotationLine).toHaveBeenCalledTimes(1));
    expect(updateQuotationLine.mock.calls[0][2]).toMatchObject({
      band_label: 'OPTIONAL ITEMS FOR OKU TOILET',
    });
  });

  it('clears a band by emptying its heading', async () => {
    listQuotationLines.mockResolvedValue([line({ band_label: 'OPTION' })]);

    renderEditor();

    const heading = await screen.findByRole('textbox', {
      name: 'Section heading on SRT-WC-01',
    });
    fireEvent.change(heading, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save SRT-WC-01' }));

    await waitFor(() => expect(updateQuotationLine).toHaveBeenCalledTimes(1));
    // Null, not an empty string: the column is nullable and a blank heading is no heading.
    expect(updateQuotationLine.mock.calls[0][2]).toMatchObject({ band_label: null });
  });

  it('reads a frozen version\'s bands and rate-only lines without offering an editor', async () => {
    listQuotationLines.mockResolvedValue([
      line({
        version_id: 'v1',
        band_label: 'BILL NO 3 PAGE 15/4',
        is_rate_only: true,
      }),
    ]);

    renderEditor();
    fireEvent.click(await screen.findByRole('button', { name: 'v1 (frozen)' }));

    expect(await screen.findByText('BILL NO 3 PAGE 15/4')).toBeInTheDocument();
    expect(screen.getByText('rate only')).toBeInTheDocument();
    expect(
      screen.queryByRole('textbox', { name: 'Section heading on SRT-WC-01' }),
    ).toBeNull();
    expect(screen.queryByRole('checkbox', { name: 'Rate only on SRT-WC-01' })).toBeNull();
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
      // Every printed column travels with the save, whether or not it was typed into: a body
      // that omitted them would leave the document's own fields behind on an unrelated edit.
      item_label: null,
      brand_snapshot: null,
      technical_spec: null,
      complete_set: null,
      band_label: null,
      is_rate_only: false,
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
      item_label: null,
      brand_snapshot: null,
      technical_spec: null,
      complete_set: null,
      band_label: null,
      is_rate_only: false,
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
