/**
 * S3 + #1341 - QuotationVersionEditor (AC-E2, AC-E3, AC-E4, AC-E7), now a READ.
 *
 * Two rules are pinned here.
 *
 * The first is unchanged: editability comes from the SERVER's `is_current` / `is_editable`, never
 * from a local guess such as "the highest number I can see". A superseded version is a document
 * the customer already holds, so it renders read-only WITH the reason, not merely with its
 * buttons missing.
 *
 * The second is #1341's: the editor is a read, always. Editing a scope's lines happens in the
 * quotation form page ("Edit quotation means I edit the whole quotation"), whose line editor is
 * pinned in `QuotationLinesGrid.test.tsx` and `QuotationFormClient.test.tsx`. The lines here are
 * the system DataGrid.
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
const deleteQuotationLine = vi.fn();
const replaceQuotationLines = vi.fn();
const recomputeQuotationVersion = vi.fn();
const judgeQuotationLine = vi.fn();

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
    deleteQuotationLine: (...args: unknown[]) => deleteQuotationLine(...args),
    replaceQuotationLines: (...args: unknown[]) => replaceQuotationLines(...args),
    recomputeQuotationVersion: (...args: unknown[]) => recomputeQuotationVersion(...args),
    judgeQuotationLine: (...args: unknown[]) => judgeQuotationLine(...args),
  };
});

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

// The product picker hits the shared products `/select` endpoint when it opens. The rows it
// returns are the ones a pick has to fill the line from, so the fetch is stubbed rather than
// the component replaced.
const PRODUCTS = [
  {
    id: 'p9',
    product_code: 'SRT-BASIN-02',
    product_name: 'Counter basin',
    description: 'Vitreous china counter basin',
    brand_id: 'b1',
    base_uom_id: 'u1',
    list_price: '560.00',
  },
];
const getProductsForLineSelect = vi.fn(async () => PRODUCTS);

vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForLineSelect: () => getProductsForLineSelect(),
  getProductsForVariantSelect: vi.fn(async () => []),
}));

// Master data behind the fill: the line snapshots a brand NAME and a unit CODE, so both ids
// have to resolve before anything lands on a row. Both hooks are cached-forever queries in
// real life; here they are answered outright so a fill is deterministic.
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [{ id: 'b1', brand_name: 'SORENTO' }] }),
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({
    data: [
      { id: 'u1', uom_code: 'PCS', uom_name: 'Pieces' },
      { id: 'u2', uom_code: 'SET', uom_name: 'Sets' },
    ],
  }),
}));

import { QuotationVersionEditor, describeRecompute } from './QuotationVersionEditor';

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

function footerText(): string {
  return document.querySelector('tfoot')?.textContent ?? '';
}

/** The ITEM cell of every LINE row, skipping the section bands that span the table. */
function itemNumbers(): (string | null | undefined)[] {
  return Array.from(document.querySelectorAll('tbody tr'))
    .filter((tr) => !tr.querySelector('td[colspan]'))
    .map((tr) => tr.querySelector('td')?.textContent);
}

beforeEach(() => {
  vi.clearAllMocks();
  listQuotationVersions.mockResolvedValue(VERSIONS);
  listQuotationLines.mockResolvedValue([line()]);
  reviseQuotation.mockResolvedValue(version({ id: 'v3', version_no: 3, is_current: true }));
  createQuotationLine.mockResolvedValue(line({ id: 'l2' }));
  updateQuotationLine.mockResolvedValue(line());
  // The default live verdict: clean. Tests that need a flag override it.
  judgeQuotationLine.mockResolvedValue({
    is_non_standard: false,
    is_below_floor: false,
    floor_value: null,
    floor_level: null,
  });
});

describe('QuotationVersionEditor', () => {
  it('lands on the current version and marks the older one frozen', async () => {
    renderEditor();

    expect(await screen.findByRole('button', { name: 'v2' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'v1 (frozen)' })).toBeInTheDocument();
    // Lines are asked for on v2, not v1: current is the server's answer, not the first row.
    expect(listQuotationLines).toHaveBeenCalledWith('v2');
  });

  it('is a read: nothing to type into and nothing to press on a line (#1341)', async () => {
    renderEditor();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.getByText('RM 900.00')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('button', { name: /Add a line/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Edit line/i })).toBeNull();
    // The system DataGrid, not the hand-written line table.
    expect(screen.getByRole('table').className).toMatch(/table-fixed/);
  });

  it('turns a superseded version read-only and says where to edit instead', async () => {
    renderEditor();
    await screen.findByText('Wall-hung WC');

    fireEvent.click(screen.getByRole('button', { name: 'v1 (frozen)' }));

    expect(await screen.findByText(/Frozen\. Make changes on v2\./i)).toBeInTheDocument();
    expect(await screen.findByText('RM 900.00')).toBeInTheDocument();
  });

  it('names the revision as the way out of a version the customer holds', async () => {
    // The sentence that replaced "its lines cannot be changed. Open a revision to re-price it.",
    // which stated a fact and offered no move. Reason and next action, in one line.
    listQuotationVersions.mockResolvedValue([
      version({ id: 'v1', version_no: 1, frozen_at: '2026-07-01T02:00:00' }),
      version({ id: 'v2', version_no: 2, is_current: true, is_issued: true, is_editable: false }),
    ]);

    renderEditor();

    expect(
      await screen.findByText(/The customer holds v2\. Edit quotation opens v3/i),
    ).toBeInTheDocument();
  });

  it('says what a revise will freeze before doing it', async () => {
    renderEditor();

    // The button is chrome and arrives with the version list, but the sentence it opens counts
    // the LINES - so clicking the moment it appears asks "how many?" of a query still in flight
    // and gets nought. Wait for a line to be on screen first.
    await screen.findByText('Wall-hung WC');
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

  /**
   * The badges have to describe the row on screen, not the row as it was saved.
   *
   * This is the complaint the client raised on a real quotation: they picked BT009 from the
   * dropdown and the line kept insisting it was off-catalog, and non-standard, until the
   * save and the refetch. Both badges were being read off the stored line.
   */
  it('filters the lines by search without renumbering items or changing the total', async () => {
    listQuotationLines.mockResolvedValue([
      line({ id: 'l1', product_code: 'SRT-WC-01', description: 'Wall-hung WC', sort_order: 0 }),
      line({
        id: 'l2',
        product_id: 'p2',
        product_code: 'BM107',
        description: 'Basin tap body',
        unit_price: '100.00',
        quantity: '2.00',
        line_total: '200.00',
        sort_order: 1,
      }),
    ]);
    renderEditor();

    await screen.findByText('Wall-hung WC');
    const total = footerText();

    fireEvent.change(screen.getByRole('searchbox', { name: /search lines/i }), {
      target: { value: 'bm107' },
    });

    await waitFor(() => expect(screen.queryByText('Wall-hung WC')).not.toBeInTheDocument());
    expect(screen.getByText('Basin tap body')).toBeInTheDocument();
    expect(itemNumbers()).toEqual(['2']);
    expect(footerText()).toBe(total);
  });

  it('lays every field of a line out as a column, in the printed order', async () => {
    renderEditor();
    await screen.findByText('Wall-hung WC');

    const printed = [
      'Item',
      'Photo',
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
    expect(
      screen.getAllByRole('columnheader').map((cell) => cell.textContent?.trim()),
    ).toEqual(printed);
  });

  it('prints the words on a rate-only line, and leaves it out of the footer sum', async () => {
    listQuotationLines.mockResolvedValue([
      line(),
      line({
        id: 'l2',
        product_code: 'SRT-BIDET-09',
        unit_price: '500.00',
        quantity: '1.00',
        line_total: '500.00',
        is_rate_only: true,
        sort_order: 1,
      }),
    ]);
    renderEditor();

    expect(await screen.findByText('rate only')).toBeInTheDocument();
    expect(footerText()).toContain('RM 9,000.00');
    expect(footerText()).not.toContain('9,500');
  });

  it('draws a section heading once, as a band above the line that carries it', async () => {
    listQuotationLines.mockResolvedValue([
      line({ band_label: 'BILL NO 3 PAGE 15/4' }),
      line({ id: 'l2', product_code: 'SRT-BIDET-09', sort_order: 10 }),
    ]);
    renderEditor();

    const bands = await screen.findAllByTestId('data-grid-group-header');
    expect(bands).toHaveLength(1);
    expect(bands[0]).toHaveTextContent('BILL NO 3 PAGE 15/4');
    expect(itemNumbers()).toEqual(['1', '2']);
  });

  it('re-checks the open version against today\'s master data and says what moved', async () => {
    recomputeQuotationVersion.mockResolvedValue({
      version_id: 'v2',
      version_no: 2,
      quotation_id: 'q1',
      scope_label: 'House Units',
      line_count: 52,
      changed_count: 7,
      now_non_standard: 0,
      no_longer_non_standard: 6,
      now_below_floor: 1,
      no_longer_below_floor: 0,
      floor_changed: 0,
      unresolved_products: 0,
      changed_lines: ['SRT-WC-01', 'CWB-242'],
    });

    renderEditor();

    fireEvent.click(await screen.findByRole('button', { name: /Recheck alerts/i }));

    await waitFor(() => expect(recomputeQuotationVersion).toHaveBeenCalledWith('v2'));
    expect(
      await screen.findByText(
        '6 lines are no longer non-standard, 1 line is now below floor.',
      ),
    ).toBeInTheDocument();
    // And WHICH lines, because "6 lines" is not something anybody can go and check.
    expect(screen.getByText('SRT-WC-01, CWB-242')).toBeInTheDocument();
  });

  it('says nothing changed rather than reporting a bare success', async () => {
    recomputeQuotationVersion.mockResolvedValue({
      version_id: 'v2',
      version_no: 2,
      quotation_id: 'q1',
      scope_label: 'House Units',
      line_count: 3,
      changed_count: 0,
      now_non_standard: 0,
      no_longer_non_standard: 0,
      now_below_floor: 0,
      no_longer_below_floor: 0,
      floor_changed: 0,
      unresolved_products: 0,
      changed_lines: [],
    });

    renderEditor();

    fireEvent.click(await screen.findByRole('button', { name: /Recheck alerts/i }));

    expect(await screen.findByText(/Nothing changed\. All 3 lines already match/i)).toBeInTheDocument();
  });

  it('withholds the recheck from a frozen version, whose flags are what the customer was sent', async () => {
    listQuotationVersions.mockResolvedValue([
      version({ id: 'v2', version_no: 2, is_current: true, is_issued: true, is_editable: false }),
    ]);

    renderEditor();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Recheck alerts/i })).toBeNull();
  });

  it('withholds the recheck from a reader', async () => {
    renderEditor({ can_edit: false });

    expect(await screen.findByRole('button', { name: 'v2' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Recheck alerts/i })).toBeNull();
  });

  it('explains the lines that stayed flagged because their product is unreadable here', async () => {
    // The live shape: 46 lines of one quotation name a product row belonging to another
    // company, so this company's catalogue cannot see it and the line reads as off-catalog.
    // Nothing changes, which is correct and completely unhelpful on its own.
    recomputeQuotationVersion.mockResolvedValue({
      version_id: 'v2',
      version_no: 2,
      quotation_id: 'q1',
      scope_label: 'House Units',
      line_count: 59,
      changed_count: 0,
      now_non_standard: 0,
      no_longer_non_standard: 0,
      now_below_floor: 0,
      no_longer_below_floor: 0,
      floor_changed: 0,
      unresolved_products: 46,
      changed_lines: [],
    });

    renderEditor();

    fireEvent.click(await screen.findByRole('button', { name: /Recheck alerts/i }));

    expect(
      await screen.findByText(
        /46 lines name products this company's catalogue does not carry/i,
      ),
    ).toBeInTheDocument();
  });
});

describe('describeRecompute', () => {
  const base = {
    version_id: 'v2',
    version_no: 2,
    quotation_id: 'q1',
    line_count: 10,
    changed_count: 0,
    now_non_standard: 0,
    no_longer_non_standard: 0,
    now_below_floor: 0,
    no_longer_below_floor: 0,
    floor_changed: 0,
    unresolved_products: 0,
    changed_lines: [] as string[],
  };

  it('counts one line in the singular', () => {
    expect(describeRecompute({ ...base, no_longer_non_standard: 1, changed_count: 1 })).toBe(
      '1 line is no longer non-standard.',
    );
  });

  it('reports both directions of both alerts in one sentence', () => {
    expect(
      describeRecompute({
        ...base,
        changed_count: 4,
        no_longer_non_standard: 6,
        now_non_standard: 2,
        no_longer_below_floor: 3,
        now_below_floor: 1,
      }),
    ).toBe(
      '6 lines are no longer non-standard, 2 lines are now non-standard, 3 lines are no longer below floor, 1 line is now below floor.',
    );
  });

  it('names the floor moving under a line that did not cross it', () => {
    expect(describeRecompute({ ...base, changed_count: 2, floor_changed: 2 })).toBe(
      '2 lines picked up a different floor.',
    );
  });
});
