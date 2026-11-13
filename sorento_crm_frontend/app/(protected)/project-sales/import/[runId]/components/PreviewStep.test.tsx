/**
 * AC-PI-47 (RED): the Preview step.
 *
 * Assumed (the coder matches these):
 *   `PreviewStep` (named export) from './PreviewStep', props:
 *     run: ProjectImportRun                      (carries preview_counts)
 *     onOpenLine: (kind: 'customer' | 'project' | 'developer' | 'person') => void
 *   Tiles from `run.preview_counts`: Will create (created), Already imported (unchanged),
 *   Skipped, Needs review (needs_review), Errors (error).
 *   Rows from `listRows(runId, grid, { outcome, code, sheet })` -> { data, total }.
 *   Outcome / Reason / Sheet are `SearchableMultiSelect` filters; the Outcome one is labelled
 *   "Outcome" (aria-label or placeholder) and its option values are the outcome keys.
 *   Import is the ONLY primary (variant="primary") button on the step.
 *   A needs_review row click calls onOpenLine with the kind of its FIRST blocking code:
 *   customer_* -> customer, project_* -> project, developer_* -> developer.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

// Round 5 (REV-M4): the screen reads projects.import.run. Every test runs with both
// permissions unless it says otherwise.
const perms = vi.hoisted(() => ({
  set: new Set<string>(['projects.import.view', 'projects.import.run']),
}));
vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({
    permissions: [...perms.set],
    permissionSet: perms.set,
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: () => {},
  }),
  useHasPermission: (slug: string) => perms.set.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => perms.set.has(s)),
  PERMISSIONS_QUERY_KEY: ['my-permissions'],
}));
const nav = vi.hoisted(() => ({ search: '' }));

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/import/run-1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ data: [], items: [], total: 0 }),
  })),
}));

type MultiProps = {
  value: string[];
  onChange: (next: string[]) => void;
  options?: { value: string; label: string }[];
  placeholder?: string;
  'aria-label'?: string;
};
vi.mock('@/components/common/SearchableMultiSelect', () => {
  const Stand = (p: MultiProps) => (
    // A test stand-in for SearchableMultiSelect, driven with user.selectOptions.
    // eslint-disable-next-line no-restricted-syntax
    <select
      multiple
      aria-label={p['aria-label'] ?? p.placeholder}
      value={p.value ?? []}
      onChange={(e) => p.onChange(Array.from(e.target.selectedOptions).map((o) => o.value))}
    >
      {(p.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
  return { SearchableMultiSelect: Stand, default: Stand };
});

const service = vi.hoisted(() => ({
  listRows: vi.fn(),
  previewRun: vi.fn(),
  startImport: vi.fn(),
  getRun: vi.fn(),
}));
vi.mock('../../../_shared/services/projectImportService', () => service);

import { PreviewStep } from './PreviewStep';

const RUN_ID = '0b5c3a52-6a8e-4f6e-9f43-6a1f2f8e1c11';
const run = {
  id: RUN_ID,
  run_no: 'PIM-0002',
  filename: 'SO SUMMARY 2026.xlsx',
  status: 'previewed',
  missing_columns: [],
  preview_counts: { created: 903, updated: 0, unchanged: 7, skipped: 365, needs_review: 14, error: 2 },
  preview_codes: { customer_unmapped: 10, project_unmapped: 4 },
};

function reportRow(ps: string, outcome: string, codes: string[], n: number) {
  return {
    sheet: "JAN'26",
    row_number: n,
    ps_number: ps,
    customer: 'CUSTOMER 001 SDN BHD',
    project: 'PROJECT 001 SAMPLE NAME',
    po_number: `PO-${n}`,
    po_date: '2026-01-05',
    outcome,
    codes,
    message: null,
  };
}

// Round 5 (review minor 8): the API names the blocking kind on each row (`blocking_kind`), so
// the frontend keeps no code -> kind table. Lead sign-off; the click assertions are unchanged.
const rows = [
  { ...reportRow('PS26-0001', 'needs_review', ['customer_unmapped', 'so_not_synced'], 2), blocking_kind: 'customer' },
  { ...reportRow('PS26-0002', 'needs_review', ['project_unmapped'], 3), blocking_kind: 'project' },
  { ...reportRow('PS26-0003', 'needs_review', ['developer_conflict'], 4), blocking_kind: 'developer' },
  { ...reportRow('PS26-0004', 'needs_review', ['customer_unmapped', 'project_unmapped'], 5), blocking_kind: 'customer' },
  { ...reportRow('PS26-0005', 'created', ['project_and_po_created'], 6), blocking_kind: null },
];

const onOpenLine = vi.fn();

function renderStep() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PreviewStep run={run as never} onOpenLine={onOpenLine} />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  perms.set = new Set(['projects.import.view', 'projects.import.run']);
  nav.search = '';
  service.listRows.mockResolvedValue({ data: rows, total: rows.length });
  service.startImport.mockResolvedValue({ job_id: 'job-1' });
});

async function openFiltersIfAny(user: ReturnType<typeof userEvent.setup>) {
  const button = screen.queryByRole('button', { name: /^Filters/ });
  if (button) await user.click(button);
}

describe('PreviewStep', () => {
  it('shows the outcome tiles from preview_counts', async () => {
    renderStep();
    await screen.findByText('PS26-0001');
    for (const [label, n] of [
      ['Will create', '903'],
      ['Already imported', '7'],
      ['Skipped', '365'],
      ['Needs review', '14'],
      ['Errors', '2'],
    ]) {
      const labels = screen.getAllByText(new RegExp(`^${label}$`, 'i'));
      const tile = labels
        .map((el) => el.parentElement)
        .find((p) => (p?.textContent ?? '').includes(n));
      expect(tile, `${label} tile shows ${n}`).toBeTruthy();
    }
  });

  it('choosing two outcomes asks listRows for both', async () => {
    const user = userEvent.setup();
    renderStep();
    await screen.findByText('PS26-0001');

    await openFiltersIfAny(user);
    await user.selectOptions(screen.getByLabelText(/Outcome/i), ['needs_review', 'error']);

    await waitFor(() => {
      const last = service.listRows.mock.calls.at(-1)!;
      expect(last[0]).toBe(RUN_ID);
      expect([...(last[2]?.outcome ?? [])].sort()).toEqual(['error', 'needs_review']);
    });
  });

  it.each([
    ['PS26-0001', 'customer'],
    ['PS26-0002', 'project'],
    ['PS26-0003', 'developer'],
    ['PS26-0004', 'customer'],
  ])('clicking needs-review row %s opens the %s line', async (ps, kind) => {
    const user = userEvent.setup();
    renderStep();
    await user.click(await screen.findByText(ps));
    await waitFor(() => expect(onOpenLine).toHaveBeenCalledTimes(1));
    expect(onOpenLine.mock.calls[0][0]).toBe(kind);
  });

  it('reason labels come from the API, never from a local code table', async () => {
    // An unknown code: only the label the API sends can name it in plain words. Shape: each
    // report row carries `labels` (one per code) and the run carries `code_labels`.
    const label = 'ZZ plain test label';
    service.listRows.mockResolvedValue({
      data: [
        { ...reportRow('PS26-0009', 'skipped', ['zz_test_code'], 9), labels: [label] },
      ],
      total: 1,
    });
    const labelled = {
      ...run,
      preview_codes: { zz_test_code: 1 },
      code_labels: { zz_test_code: label },
    };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}>
        <PreviewStep run={labelled as never} onOpenLine={onOpenLine} />
      </QueryClientProvider>
    );

    const row = (await screen.findByText('PS26-0009')).closest('tr')!;
    expect(row.textContent).toContain(label);
    await openFiltersIfAny(userEvent.setup());
    const reason = screen.getByLabelText(/Reason/i) as HTMLSelectElement;
    expect(Array.from(reason.options).map((o) => o.textContent)).toContain(label);
    // Neither the raw code nor a humanised guess of it is shown.
    expect(container.textContent ?? '').not.toMatch(/zz_test_code|zz test code/i);
  });

  it('a row that needs nothing does not open a line', async () => {
    const user = userEvent.setup();
    renderStep();
    await user.click(await screen.findByText('PS26-0005'));
    expect(onOpenLine).not.toHaveBeenCalled();
  });
});

describe('PreviewStep, round 5', () => {
  it('r5: Outcome, Reason and Sheet sit inside the toolbar Filters control (REV-minor4)', async () => {
    const user = userEvent.setup();
    renderStep();
    await screen.findByText('PS26-0001');
    expect(screen.queryByLabelText(/^Outcome$/i)).toBeNull();
    await user.click(screen.getByRole('button', { name: /^Filters/ }));
    expect(await screen.findByLabelText(/^Outcome$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Reason$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Sheet$/i)).toBeInTheDocument();
  });

  it('r5: the outcome tiles include Updated (REV-minor5)', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PreviewStep
          run={{ ...run, preview_counts: { ...run.preview_counts, updated: 5 } } as never}
          onOpenLine={onOpenLine}
        />
      </QueryClientProvider>
    );
    await screen.findByText('PS26-0001');
    const tile = screen
      .getAllByText(/^Updated$/i)
      .map((el) => el.parentElement)
      .find((p) => (p?.textContent ?? '').includes('5'));
    expect(tile).toBeTruthy();
  });

  it('r5: the step body has no primary button: Import sits in the page header (REV-minor11)', async () => {
    const { container } = renderStep();
    await screen.findByText('PS26-0001');
    const primaries = Array.from(container.querySelectorAll('button')).filter((b) =>
      /(^|\s)bg-primary(\s|$)/.test(b.className)
    );
    expect(primaries).toHaveLength(0);
  });

  it.each([
    ['PS26-0101', ['zz_unknown_block'], 'developer'],
    ['PS26-0102', ['customer_unmapped'], 'project'],
  ])('r5: row %s opens the kind the API names in blocking_kind (REV-minor8)', async (ps, codes, kind) => {
    const user = userEvent.setup();
    service.listRows.mockResolvedValue({
      data: [{ ...reportRow(ps, 'needs_review', codes, 7), blocking_kind: kind, labels: ['x'] }],
      total: 1,
    });
    renderStep();
    await user.click(await screen.findByText(ps));
    await waitFor(() => expect(onOpenLine).toHaveBeenCalledTimes(1));
    expect(onOpenLine.mock.calls[0][0]).toBe(kind);
  });
});

/** Round 6 D3/D8: the page content width at 1280 with the sidebar open: 1280 - 270 sidebar
 *  (demo6 `--sidebar-width`) - 15 shell margin - 48 page padding - 2 borders. */
const CONTENT_WIDTH_1280 = 945;

function headerCells(container: HTMLElement): HTMLTableCellElement[] {
  return Array.from(container.querySelectorAll('table thead th')) as HTMLTableCellElement[];
}

function widthOf(cell: HTMLElement | null | undefined): number {
  return cell ? parseFloat(cell.style.width || '0') : 0;
}

function headerCell(container: HTMLElement, text: RegExp): HTMLTableCellElement | undefined {
  return headerCells(container).find((th) => text.test((th.textContent ?? '').trim()));
}

describe('PreviewStep, round 6', () => {
  it('r6: D4 a needs-review row passes its blocking line to onOpenLine', async () => {
    const user = userEvent.setup();
    const line = { kind: 'customer', customer_value_key: '', value_key: 'CUSTOMER 013 SDN BHD' };
    service.listRows.mockResolvedValue({
      data: [{ ...reportRow('PS26-0013', 'needs_review', ['customer_unmapped'], 13),
               blocking_kind: 'customer', blocking_line: line, labels: ['Customer not linked yet'] }],
      total: 1,
    });
    renderStep();
    await user.click(await screen.findByText('PS26-0013'));
    await waitFor(() => expect(onOpenLine).toHaveBeenCalledTimes(1));
    expect(onOpenLine.mock.calls[0][0]).toBe('customer');
    expect(onOpenLine.mock.calls[0][1]).toEqual(line);
  });

  it('r6: D3 PS no. and PO date fit at their default size', async () => {
    const { container } = renderStep();
    await screen.findByText('PS26-0001');
    // 'PS26-0000' / 'dd/mm/yyyy' at the grid's font with cell padding and the sort control.
    expect(widthOf(headerCell(container, /^PS no\./))).toBeGreaterThanOrEqual(120);
    expect(widthOf(headerCell(container, /^PO date/))).toBeGreaterThanOrEqual(120);
  });

  it('r6: D3 the default columns, Outcome and Reason included, fit the 1280 content width', async () => {
    const { container } = renderStep();
    await screen.findByText('PS26-0001');
    expect(headerCell(container, /^Outcome/)).toBeTruthy();
    expect(headerCell(container, /^Reason/)).toBeTruthy();
    const total = headerCells(container).reduce((sum, th) => sum + widthOf(th), 0);
    expect(total).toBeLessThanOrEqual(CONTENT_WIDTH_1280);
  });
});

/** Round 7: a cell's full text is on hover: the cell (or its wrapper) carries title=text. */
function hasFullTitle(container: HTMLElement, text: string): boolean {
  const cells = Array.from(container.querySelectorAll('table tbody td'));
  return cells.some((td) => {
    if ((td.textContent ?? '').trim() !== text) return false;
    return [td, ...Array.from(td.querySelectorAll('*'))].some(
      (el) => el.getAttribute('title') === text
    );
  });
}

function isTruncated(container: HTMLElement, text: string): boolean {
  const cells = Array.from(container.querySelectorAll('table tbody td'));
  const td = cells.find((c) => (c.textContent ?? '').trim() === text);
  if (!td) return true;
  return [td, ...Array.from(td.querySelectorAll('*'))].some((el) =>
    /(^|\s)(truncate|text-ellipsis|line-clamp-1)(\s|$)/.test((el as HTMLElement).className ?? '')
  );
}

describe('PreviewStep, round 7', () => {
  const longRow = {
    ...reportRow('PS26-0042', 'skipped', ['no_project_name'], 42),
    sheet: "JUN'26 ",
    customer: 'CUSTOMER 042 SENDIRIAN BERHAD',
    project: 'PROJECT 042 SAMPLE NAME WITH A LONG TAIL',
    po_number: 'UT12/0042/LONG-REF',
    po_date: '2026-06-12',
    labels: ['No project name'],
    message: null,
  };

  it.each([
    ['Customer', 'CUSTOMER 042 SENDIRIAN BERHAD'],
    ['Project', 'PROJECT 042 SAMPLE NAME WITH A LONG TAIL'],
    ['PO no.', 'UT12/0042/LONG-REF'],
    ['Reason', 'No project name'],
  ])('r7: N2 a cut %s cell shows its full text on hover', async (_column, text) => {
    service.listRows.mockResolvedValue({ data: [longRow], total: 1 });
    const { container } = renderStep();
    await screen.findByText('PS26-0042');
    expect(hasFullTitle(container, text)).toBe(true);
  });

  it('r7: N2 the Sheet cell shows the sheet name in full on hover', async () => {
    service.listRows.mockResolvedValue({ data: [longRow], total: 1 });
    const { container } = renderStep();
    await screen.findByText('PS26-0042');
    expect(hasFullTitle(container, "JUN'26")).toBe(true);
  });

  it('r7: N2 PS no. and PO date never truncate', async () => {
    service.listRows.mockResolvedValue({ data: [longRow], total: 1 });
    const { container } = renderStep();
    await screen.findByText('PS26-0042');
    expect(isTruncated(container, 'PS26-0042')).toBe(false);
    expect(isTruncated(container, '12/06/2026')).toBe(false);
  });
});
