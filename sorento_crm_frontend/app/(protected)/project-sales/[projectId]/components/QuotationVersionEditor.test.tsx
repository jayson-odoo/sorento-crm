/**
 * S3 + S11 - QuotationVersionEditor (AC-E2, AC-E3, AC-E4, AC-E7).
 *
 * Two rules are pinned here.
 *
 * The first is unchanged: editability comes from the SERVER's `is_current` / `is_editable`, never
 * from a local guess such as "the highest number I can see". A superseded version is a document
 * the customer already holds, so it renders read-only WITH the reason, not merely with its
 * buttons missing.
 *
 * The second is S11's, and it replaces the per-row saving these specs used to assert. The editor
 * no longer writes ANYTHING: without an edit session it is a clean read, and with one it stages.
 * So every claim that used to end in "and it called updateQuotationLine" now ends in "and this is
 * the body the one bulk write will carry", which is the same guarantee one level up. The write
 * itself is the document screen's, and is pinned in `QuotationDocumentClient.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  Project,
  ProjectQuotation,
  QuotationLine,
  QuotationVersion,
} from '../../_shared/types/project.types';
import {
  useQuotationEditSession,
  type QuotationEditSession,
} from '../quotation-documents/[documentId]/components/useQuotationEditSession';

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

import {
  QuotationVersionEditor,
  describeRecompute,
  stagedLinesToBody,
  stagedScopeTotal,
} from './QuotationVersionEditor';

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

/**
 * The document screen, reduced to the one thing the editor depends on: a real edit session,
 * living OUTSIDE the editor.
 *
 * The real hook rather than a hand-rolled stub, because the round trip is the thing under test -
 * the table reports, the session holds, and the editor is re-seeded from what the session holds.
 * A stub that simply echoed would prove none of that.
 */
let session: QuotationEditSession | null = null;

function Harness({
  projectOverrides,
  editing,
}: {
  projectOverrides: Partial<Project>;
  editing: boolean;
}) {
  const held = useQuotationEditSession();
  session = held;
  const { begin, isEditing, scopes, seedScope, stageScope, toggleRemoved } = held;

  React.useEffect(() => {
    if (editing) begin();
  }, [begin, editing]);

  const edit = React.useMemo(
    () =>
      isEditing
        ? {
            staged: scopes[QUOTATION.id]?.lines ?? null,
            seed: (versionId: string, lines: Parameters<typeof seedScope>[2]) =>
              seedScope(QUOTATION.id, versionId, lines),
            stage: (lines: Parameters<typeof stageScope>[1]) =>
              stageScope(QUOTATION.id, lines),
            toggleRemoved: (key: string) => toggleRemoved(QUOTATION.id, key),
          }
        : null,
    [isEditing, scopes, seedScope, stageScope, toggleRemoved],
  );

  return (
    <QuotationVersionEditor
      project={project(projectOverrides)}
      quotation={QUOTATION}
      edit={edit}
    />
  );
}

function renderEditor(overrides: Partial<Project> = {}, editing = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Harness projectOverrides={overrides} editing={editing} />
    </QueryClientProvider>,
  );
}

/** The screen in an open edit session, which is the only place cells exist. */
async function renderEditing(overrides: Partial<Project> = {}) {
  const result = renderEditor(overrides, true);
  await screen.findByRole('button', { name: /Add a line/i });
  return result;
}

/** What the one bulk write would carry if Save were pressed right now. */
function stagedBody() {
  return stagedLinesToBody(session?.scopes[QUOTATION.id]?.lines ?? []);
}

/** What the table's footer says right now, add buttons and all. */
function footerText(): string {
  return screen.getByRole('table').querySelector('tfoot')?.textContent ?? '';
}

/** The ITEM cell of every LINE row, skipping the section headings that span the table. */
function itemNumbers(): (string | null | undefined)[] {
  return Array.from(screen.getByRole('table').querySelectorAll('tbody tr'))
    .filter((tr) => !tr.querySelector('td[colspan]'))
    .map((tr) => tr.querySelector('td')?.textContent);
}

/** Nothing left the browser. Every write path the editor used to own is asserted silent. */
function expectNothingWritten() {
  expect(createQuotationLine).not.toHaveBeenCalled();
  expect(updateQuotationLine).not.toHaveBeenCalled();
  expect(deleteQuotationLine).not.toHaveBeenCalled();
  expect(replaceQuotationLines).not.toHaveBeenCalled();
}

beforeEach(() => {
  vi.clearAllMocks();
  session = null;
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

  it('reads as a document until somebody opens an edit session', async () => {
    // The client's complaint in one assertion: a screen you are reading must not be a screen
    // that saves under you. There is nothing to type into and nothing to press by accident.
    renderEditor();

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.getByText('RM 900.00')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Qty on SRT-WC-01' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Add a line/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Remove SRT-WC-01/i })).toBeNull();
  });

  it('lets the current version be edited in place, without a dialog', async () => {
    await renderEditing();

    // The line IS the row: every field is a cell, so there is nothing to open.
    expect(screen.getByRole('textbox', { name: 'Description on SRT-WC-01' })).toHaveValue(
      'Wall-hung WC',
    );
    expect(screen.getByRole('textbox', { name: 'Qty on SRT-WC-01' })).toHaveValue('10.00');
    expect(screen.queryByRole('button', { name: /Edit SRT-WC-01/i })).toBeNull();
    // And no per-row save affordance, because there is one Save for the whole document now.
    expect(screen.queryByRole('button', { name: /^Save SRT-WC-01$/ })).toBeNull();
  });

  it('turns a superseded version read-only and says where to edit instead', async () => {
    await renderEditing();

    fireEvent.click(screen.getByRole('button', { name: 'v1 (frozen)' }));

    // One line, not a paragraph on why versions freeze: the consequence is the useful part.
    expect(await screen.findByText(/Frozen\. Make changes on v2\./i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add a line/i })).toBeNull();
    expect(screen.queryByRole('textbox', { name: 'Qty on SRT-WC-01' })).toBeNull();
    // Frozen lines still read as money and quantities, not as raw API strings.
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
      await screen.findByText(/The customer holds v2\. Edit opens v3/i),
    ).toBeInTheDocument();
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

  /**
   * The badges have to describe the row on screen, not the row as it was saved.
   *
   * This is the complaint the client raised on a real quotation: they picked BT009 from the
   * dropdown and the line kept insisting it was off-catalog, and non-standard, until the
   * save and the refetch. Both badges were being read off the stored line.
   */
  it('clears Off-catalog the moment a product is picked, before any save', async () => {
    listQuotationLines.mockResolvedValue([
      line({ product_code: null, product_id: null, description: 'BT009', is_non_standard: true }),
    ]);
    await renderEditing();

    expect(screen.getByText('Off-catalog')).toBeInTheDocument();

    // Pick a product on the line. `Off-catalog` means "no product is linked" and nothing
    // else, so it is a fact about the draft and can be answered here.
    fireEvent.click(screen.getByRole('combobox', { name: /^Product on / }));
    fireEvent.click(await screen.findByRole('option', { name: /SRT-BASIN-02/ }));

    await waitFor(() => expect(screen.queryByText('Off-catalog')).not.toBeInTheDocument());
  });

  it('asks the server for a fresh verdict the moment the product changes - on the spot, not at save', async () => {
    // The client's requirement verbatim: "cannot wait until I save then only compute". The
    // verdicts still come from the SERVER (series membership counts nominated categories the
    // browser never fetched), but they are asked for per settled draft, debounced, with the
    // same functions the save runs. Here the picked product is outside the series, so the
    // flag must appear BEFORE any save - the BM107 case.
    listQuotationLines.mockResolvedValue([
      line({
        product_id: 'p-old',
        product_code: 'SRTWC8608-SC',
        is_non_standard: false,
        is_below_floor: false,
      }),
    ]);
    judgeQuotationLine.mockResolvedValue({
      is_non_standard: true,
      is_below_floor: false,
      floor_value: null,
      floor_level: null,
    });
    await renderEditing();

    expect(screen.queryByText('Non-standard')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('combobox', { name: /^Product on / }));
    fireEvent.click(await screen.findByRole('option', { name: /SRT-BASIN-02/ }));

    // Debounced 400ms, then judged. NOTHING was saved on the way to the badge.
    expect(await screen.findByText('Non-standard', {}, { timeout: 5000 })).toBeInTheDocument();
    expect(judgeQuotationLine).toHaveBeenCalledWith(
      QUOTATION.id,
      expect.objectContaining({ product_id: 'p9' }),
    );
    expect(replaceQuotationLines).not.toHaveBeenCalled();
    expect(updateQuotationLine).not.toHaveBeenCalled();
  });

  it('flags a price below the floor as it is typed, with the floor named', async () => {
    listQuotationLines.mockResolvedValue([line({ unit_price: '900.00' })]);
    judgeQuotationLine.mockResolvedValue({
      is_non_standard: false,
      is_below_floor: true,
      floor_value: '94.00',
      floor_level: 'series',
    });
    await renderEditing();

    expect(screen.queryByText('Below floor')).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: 'Unit price on SRT-WC-01' }), {
      target: { value: '90.00' },
    });

    expect(await screen.findByText('Below floor', {}, { timeout: 5000 })).toBeInTheDocument();
    // The floor is NAMED, so the refusal can be argued with rather than merely obeyed.
    expect(screen.getByText(/Floor is RM ?94\.00/)).toBeInTheDocument();
    expect(judgeQuotationLine).toHaveBeenCalledWith(
      QUOTATION.id,
      expect.objectContaining({ unit_price: '90.00' }),
    );
  });


  /**
   * Search over the lines - a 59-line version cannot be found in by eye, and Ctrl-F only
   * finds what is scrolled into the DOM.
   *
   * The design claim under test: a hidden row is HIDDEN, not removed. Item numbers hold and
   * the footer total does not move, because "item 12" on the customer's paper must not
   * become "item 3", and a total that shrank with the view would read as lines lost.
   */
  it('filters the lines by search without renumbering items or changing the total', async () => {
    listQuotationLines.mockResolvedValue([
      line({ id: 'l1', product_code: 'SRT-WC-01', description: 'Wall-hung WC', sort_order: 0 }),
      line({
        id: 'l2',
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
    const total = screen.getByRole('table').querySelector('tfoot')?.textContent ?? '';

    fireEvent.change(screen.getByLabelText(/search lines/i), {
      target: { value: 'bm107' },
    });

    await waitFor(() => expect(screen.queryByText('Wall-hung WC')).not.toBeInTheDocument());
    expect(screen.getByText('Basin tap body')).toBeInTheDocument();
    // The surviving row keeps its own item number: it is still line 2.
    expect(itemNumbers()).toEqual(['2']);
    // And the money did not move - the hidden line is hidden, not gone.
    expect(screen.getByRole('table').querySelector('tfoot')?.textContent).toBe(total);
  });

  it('says the search found nothing rather than looking like an empty version', async () => {
    listQuotationLines.mockResolvedValue([line()]);
    renderEditor();

    await screen.findByText('Wall-hung WC');
    fireEvent.change(screen.getByLabelText(/search lines/i), {
      target: { value: 'zzt-no-such-line' },
    });

    expect(
      await screen.findByText(/no line matches "zzt-no-such-line"/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/frozen without any lines|nothing quoted yet/i)).not.toBeInTheDocument();
  });

  it('lays every field of a line out as a column, in the printed order', async () => {
    await renderEditing();

    // The order matters: the row is filled in reading left to right the way the customer
    // reads the printed quotation back.
    const printed = [
      'Item',
      // Column B of the client's own issued quotation, immediately after ITEM (S21).
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
    for (const header of printed) {
      expect(await screen.findByRole('columnheader', { name: header })).toBeInTheDocument();
    }
    expect(
      screen.getAllByRole('columnheader').map((cell) => cell.textContent?.trim()),
    ).toEqual([...printed, 'Row actions']);
    // Notes is a paragraph, so it keeps a home off the row rather than a six-character cell.
    expect(screen.getByRole('button', { name: 'Notes on SRT-WC-01' })).toBeInTheDocument();
  });

  it('holds the printed columns as cells, and stages every one of them', async () => {
    listQuotationLines.mockResolvedValue([
      line({
        brand: 'SORENTO',
        technical_spec: 'Rimless, 4/2.6L dual flush',
        complete_set: 'c/w seat cover',
      }),
    ]);

    await renderEditing();

    // What the server sent is on screen, under the name the RESPONSE uses for it.
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

    // The REQUEST calls the brand `brand_snapshot` while the response calls it `brand`. The
    // asymmetry is the API's, and the editor honours it rather than sending its own name.
    await waitFor(() =>
      expect(stagedBody()[0]).toMatchObject({
        id: 'l1',
        brand_snapshot: 'MOCHA',
        technical_spec: 'Rimless, 4/2.6L dual flush',
        complete_set: 'c/w seat cover',
      }),
    );
    // The item number is the row's position, so there is nothing to send: a stored label
    // could only ever disagree with what is printed.
    expect(stagedBody()[0]).not.toHaveProperty('item_label');
    expectNothingWritten();
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

    await renderEditing();

    expect(screen.getByText('rate only')).toBeInTheDocument();
    // Never RM 0.00, which reads as free, and never blank, which reads as a fault.
    expect(screen.queryByText('RM 0.00')).toBeNull();
    expect(screen.queryByText('RM 500.00')).toBeNull();
    // The footer under the money column is the other line alone, not RM 9,500.00.
    expect(footerText()).toContain('RM 9,000.00');
    expect(footerText()).not.toContain('9,500');
    expect(
      screen.getByRole('checkbox', { name: 'Rate only on SRT-BIDET-09' }),
    ).toBeChecked();
  });

  it('marks a line rate-only from its own row, and says so in the total column', async () => {
    await renderEditing();

    const toggle = screen.getByRole('checkbox', { name: 'Rate only on SRT-WC-01' });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);

    // The total column answers immediately, off the draft, before anything is saved.
    expect(screen.getByText('rate only')).toBeInTheDocument();

    await waitFor(() => expect(stagedBody()[0]).toMatchObject({ is_rate_only: true }));
    expectNothingWritten();
  });

  it('opens a section with one heading above the line that carries it', async () => {
    listQuotationLines.mockResolvedValue([
      line({ band_label: 'BILL NO 3 PAGE 15/4' }),
      line({ id: 'l2', product_code: 'SRT-BIDET-09', sort_order: 10 }),
    ]);

    await renderEditing();

    const heading = screen.getByRole('textbox', { name: 'Section heading on SRT-WC-01' });
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

  it('opens a section from the footer, beside adding a line', async () => {
    await renderEditing();

    // Two buttons, side by side, where "Add a line" already was. The per-row icon that used to
    // turn a line into a heading is gone: the client called it counterintuitive.
    expect(screen.getByRole('button', { name: 'Add a line' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add a section' }));

    const heading = await screen.findByRole('textbox', {
      name: 'Section heading on line 2',
    });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    fireEvent.change(heading, { target: { value: 'OPTIONAL ITEMS FOR OKU TOILET' } });
    // The line under the heading is ready to fill in: a section IS a line.
    fireEvent.change(screen.getByRole('textbox', { name: 'Description on line 2' }), {
      target: { value: 'Grab bar' },
    });

    await waitFor(() =>
      expect(stagedBody()[1]).toMatchObject({
        band_label: 'OPTIONAL ITEMS FOR OKU TOILET',
        description_snapshot: 'Grab bar',
      }),
    );
    expectNothingWritten();
  });

  it('clears a band by emptying its heading', async () => {
    listQuotationLines.mockResolvedValue([line({ band_label: 'OPTION' })]);

    await renderEditing();

    const heading = screen.getByRole('textbox', { name: 'Section heading on SRT-WC-01' });
    fireEvent.change(heading, { target: { value: '' } });

    // Null, not an empty string: the column is nullable and a blank heading is no heading.
    await waitFor(() => expect(stagedBody()[0]).toMatchObject({ band_label: null }));
  });

  it("reads a frozen version's bands and rate-only lines without offering an editor", async () => {
    listQuotationLines.mockResolvedValue([
      line({
        version_id: 'v1',
        band_label: 'BILL NO 3 PAGE 15/4',
        is_rate_only: true,
      }),
    ]);

    await renderEditing();
    fireEvent.click(screen.getByRole('button', { name: 'v1 (frozen)' }));

    expect(await screen.findByText('BILL NO 3 PAGE 15/4')).toBeInTheDocument();
    expect(screen.getByText('rate only')).toBeInTheDocument();
    expect(
      screen.queryByRole('textbox', { name: 'Section heading on SRT-WC-01' }),
    ).toBeNull();
    expect(screen.queryByRole('checkbox', { name: 'Rate only on SRT-WC-01' })).toBeNull();
  });

  it('moves the line total while the quantity is typed, before anything is saved', async () => {
    await renderEditing();

    const qty = screen.getByRole('textbox', { name: 'Qty on SRT-WC-01' });
    fireEvent.change(qty, { target: { value: '3' } });

    // In the ROW's own Total cell. The footer says the same figure now that it tracks the
    // drafts too, so this pins where the number is rather than that it exists somewhere.
    const body = screen.getByRole('table').querySelector('tbody') as HTMLElement;
    expect(within(body).getByText('RM 2,700.00')).toBeInTheDocument();
    expectNothingWritten();
  });

  it('stages an edited line with the body the bulk write will carry', async () => {
    await renderEditing();

    const qty = screen.getByRole('textbox', { name: 'Qty on SRT-WC-01' });
    fireEvent.change(qty, { target: { value: '12' } });

    await waitFor(() =>
      expect(stagedBody()).toEqual([
        {
          // The id is what tells the whole-set write this line already exists. Without it the
          // server would insert a second copy and delete the original.
          id: 'l1',
          product_id: null,
          description_snapshot: 'Wall-hung WC',
          unit_price: '900.00',
          quantity: '12',
          uom: null,
          unit_type: null,
          notes: null,
          // Every printed column travels with the save, whether or not it was typed into: a body
          // that omitted them would leave the document's own fields behind on an unrelated edit.
          brand_snapshot: null,
          technical_spec: null,
          complete_set: null,
          band_label: null,
          is_rate_only: false,
        },
      ]),
    );
    expectNothingWritten();
  });

  it('stages an added line with no id, so the write reads it as new', async () => {
    await renderEditing();

    fireEvent.click(screen.getByRole('button', { name: 'Add a line' }));
    const description = await screen.findByRole('textbox', {
      name: 'Description on line 2',
    });
    fireEvent.change(description, { target: { value: 'Bespoke vanity top' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Unit price on line 2' }), {
      target: { value: '1250.00' },
    });

    await waitFor(() => expect(stagedBody()).toHaveLength(2));
    expect(stagedBody()[1]).toEqual({
      product_id: null,
      description_snapshot: 'Bespoke vanity top',
      unit_price: '1250.00',
      quantity: '1',
      uom: null,
      unit_type: null,
      notes: null,
      brand_snapshot: null,
      technical_spec: null,
      complete_set: null,
      band_label: null,
      is_rate_only: false,
    });
    // Position in the array is the order, so there is no sort_order to disagree with it.
    expect(stagedBody()[1]).not.toHaveProperty('sort_order');
    expect(stagedBody()[1]).not.toHaveProperty('id');
    expectNothingWritten();
  });

  it('marks the cell that stops an off-catalog line from being saved', async () => {
    await renderEditing();

    fireEvent.click(screen.getByRole('button', { name: 'Add a line' }));
    const description = await screen.findByRole('textbox', {
      name: 'Description on line 2',
    });
    // Typed into, so it is real data rather than a mis-click, but it has neither a product
    // nor a description to stand in for one. Marked as it is typed, not held back until Save:
    // hunting for the bad row afterwards, in a scope of fifty, is the worse of the two.
    fireEvent.change(screen.getByRole('textbox', { name: 'Qty on line 2' }), {
      target: { value: '4' },
    });

    expect(await screen.findByText('Needed on an off-catalog line')).toBeInTheDocument();
    expect(description).toHaveAttribute('aria-invalid', 'true');
    expectNothingWritten();
  });

  it('leaves an added row nobody has typed into unmarked', async () => {
    await renderEditing();

    fireEvent.click(screen.getByRole('button', { name: 'Add a line' }));
    await screen.findByRole('textbox', { name: 'Description on line 2' });

    // Empty is not wrong. Marking a row red the instant it appears would be the screen
    // shouting at somebody for pressing the button it offered them.
    expect(screen.queryByText('Needed on an off-catalog line')).toBeNull();
  });

  it('fills the line from the product that was picked', async () => {
    await renderEditing();

    fireEvent.click(screen.getByRole('combobox', { name: 'Product on SRT-WC-01' }));
    fireEvent.click(await screen.findByRole('option', { name: /SRT-BASIN-02/ }));

    // One decision answers the rest of the row, off the product record rather than off memory.
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: 'Description on SRT-WC-01' })).toHaveValue(
        'Vitreous china counter basin',
      ),
    );
    expect(screen.getByRole('textbox', { name: 'Brand on SRT-WC-01' })).toHaveValue('SORENTO');
    expect(screen.getByRole('combobox', { name: 'UOM on SRT-WC-01' })).toHaveTextContent('PCS');
    // And the list price beside the unit price is the picked product's, at once: reading the
    // saved row instead is what left "List RM 0.00" next to a real product.
    expect(screen.getByText('List RM 560.00')).toBeInTheDocument();
    // The trigger names the product that was PICKED. Nothing refetches during an edit session,
    // so resolving it from the stored line would leave the old code on screen until Save.
    expect(screen.getByRole('combobox', { name: 'Product on SRT-WC-01' })).toHaveTextContent(
      'SRT-BASIN-02',
    );
    expectNothingWritten();
  });

  it("lets the picked product overwrite a description somebody typed", async () => {
    // The client chose predictability: one product means one set of fields, every time,
    // including over an edit made before the re-pick. The cost was stated and accepted.
    await renderEditing();

    const description = screen.getByRole('textbox', { name: 'Description on SRT-WC-01' });
    fireEvent.change(description, { target: { value: 'Wording agreed with the QS' } });

    fireEvent.click(screen.getByRole('combobox', { name: 'Product on SRT-WC-01' }));
    fireEvent.click(await screen.findByRole('option', { name: /SRT-BASIN-02/ }));

    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: 'Description on SRT-WC-01' })).toHaveValue(
        'Vitreous china counter basin',
      ),
    );
  });

  it('numbers the items 1, 2, 3, 4 straight through the sections', async () => {
    // Continuous within the SCOPE, not restarted per heading: that is how the customer's own
    // bill of quantities reads, and a per-section restart is the easy thing to write by
    // accident. Two sections of two lines read 1, 2 then 3, 4.
    listQuotationLines.mockResolvedValue([
      line({ id: 'l1', product_code: 'A-1', band_label: 'BILL NO 3', sort_order: 0 }),
      line({ id: 'l2', product_code: 'A-2', sort_order: 10 }),
      line({ id: 'l3', product_code: 'B-1', band_label: 'OPTIONAL ITEMS', sort_order: 20 }),
      line({ id: 'l4', product_code: 'B-2', sort_order: 30 }),
    ]);

    await renderEditing();

    expect(itemNumbers()).toEqual(['1', '2', '3', '4']);
    // Nothing to type into: the number is the row's position, not a field.
    expect(screen.queryByRole('textbox', { name: 'Item on A-1' })).toBeNull();
  });

  it('moves the footer total while a quantity is typed, before anything is saved', async () => {
    await renderEditing();

    const qty = screen.getByRole('textbox', { name: 'Qty on SRT-WC-01' });
    expect(footerText()).toContain('RM 9,000.00');

    fireEvent.change(qty, { target: { value: '3' } });

    // The bottom line follows the cells above it. Off the STRINGS, to the cent.
    expect(footerText()).toContain('RM 2,700.00');
    expectNothingWritten();
  });

  it('drops a line out of the live total the moment it is marked rate only', async () => {
    listQuotationLines.mockResolvedValue([
      line(),
      line({
        id: 'l2',
        product_code: 'SRT-BIDET-09',
        unit_price: '500.00',
        quantity: '1.00',
        line_total: '500.00',
      }),
    ]);

    await renderEditing();

    expect(footerText()).toContain('RM 9,500.00');

    fireEvent.click(screen.getByRole('checkbox', { name: 'Rate only on SRT-BIDET-09' }));

    // The customer is still shown the rate; nobody adds it up. Same rule as the PDF.
    expect(footerText()).toContain('RM 9,000.00');
    expectNothingWritten();
  });

  it('leaves the staged set and the footer summing to the same figure', async () => {
    // The header outside this editor sums the STAGED lines itself now, instead of being told a
    // figure on the way in and having it cleared on the way out. One mechanism, so the claim
    // worth pinning is that the two readings of the same drafts agree.
    await renderEditing();

    fireEvent.change(screen.getByRole('textbox', { name: 'Qty on SRT-WC-01' }), {
      target: { value: '3' },
    });

    await waitFor(() =>
      expect(stagedScopeTotal(session?.scopes[QUOTATION.id]?.lines ?? [])).toBe('2700.00'),
    );
    expect(footerText()).toContain('RM 2,700.00');
  });

  it('strikes a removed line through instead of asking, and puts it back on request', async () => {
    // Removing inside an edit session destroys nothing, so it asks nothing. The row stays where
    // it is, struck through, because a removal that is invisible cannot be taken back.
    await renderEditing();

    fireEvent.click(screen.getByRole('button', { name: 'Remove SRT-WC-01' }));

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(await screen.findByText('Removed on save')).toBeInTheDocument();
    expect(screen.getByText('Wall-hung WC')).toBeInTheDocument();
    // Out of the money the moment it is marked: the footer states what will actually be charged.
    expect(footerText()).toContain('RM 0.00');
    // And out of the body the write would carry.
    await waitFor(() => expect(stagedBody()).toEqual([]));

    fireEvent.click(screen.getByRole('button', { name: 'Restore SRT-WC-01' }));

    await waitFor(() => expect(stagedBody()).toHaveLength(1));
    expect(footerText()).toContain('RM 9,000.00');
    expectNothingWritten();
  });

  it('offers no write affordance to a reader', async () => {
    renderEditor({ can_edit: false });

    expect(await screen.findByRole('button', { name: 'v2' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Revise/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Add a line/i })).toBeNull();
  });

  it('keeps a version the server froze read-only even inside an edit session', async () => {
    // Edit is a screen state; `is_editable` is the server's answer. The screen state never wins.
    listQuotationVersions.mockResolvedValue([
      version({ id: 'v2', version_no: 2, is_current: true, is_issued: true, is_editable: false }),
    ]);

    renderEditor({}, true);

    expect(await screen.findByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Qty on SRT-WC-01' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Add a line/i })).toBeNull();
  });

  /**
   * S19 - the recompute control.
   *
   * The point is not that a request goes out; it is that the ANSWER is on screen. The
   * client's own words were "a refresh button that recompute this", and a silent success
   * toast over 46 corrected flags tells them nothing about what moved.
   */
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

  it('disables the recheck while an edit session is open, so staged rows cannot go stale', async () => {
    await renderEditing();

    expect(screen.getByRole('button', { name: /Recheck alerts/i })).toBeDisabled();
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
