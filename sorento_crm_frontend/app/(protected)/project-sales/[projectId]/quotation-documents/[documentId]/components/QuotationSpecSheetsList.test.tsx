/**
 * SPEC-SHEET-V2 red test 16: the Spec sheet tab is a list of saved spec sheets.
 *
 * Written BEFORE the component. Contract of this file:
 *
 *   Component   `QuotationSpecSheetsList` (named export of ./QuotationSpecSheetsList), no props; it
 *               reads `{ projectId, documentId, canEdit }` from `useQuotationDocumentScreen()`.
 *   Service     `@/app/(protected)/project-sales/_shared/services/specSheetService` exports exactly:
 *                 listSpecSheets(projectId, documentId)
 *                 createSpecSheet(projectId, documentId, body)
 *                 getSpecSheet(projectId, documentId, sheetId)
 *                 updateSpecSheet(projectId, documentId, sheetId, body)
 *                 getSpecSheetPreview(projectId, documentId, sheetId, keys)
 *                 getSpecSheetPageDesign(projectId, documentId, sheetId, key)
 *                 saveSpecSheetPageEdit(projectId, documentId, sheetId, key, layers)
 *                 queueSpecSheetPdf(projectId, documentId, sheetId)
 *   List        `PanelDataGrid`, `rowHref` to `/project-sales/<p>/quotation-documents/<d>/spec-sheet/<id>`,
 *               a row menu (`RowActionsMenu`, trigger named "... actions") with View, Export PDF and
 *               Delete. Delete goes through `useDeferredAction` with actionKey
 *               `quotation_spec_sheet.delete`, entityType `quotation_spec_sheet`: no confirm dialog.
 *   Header      one CTA "Create spec sheet", disabled with `create_disabled_reason` as its title.
 *   Empty       heading "No spec sheets yet" (or "No lines yet" when the reason is set), no button in
 *               the body.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
if (!(globalThis as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents/d1/spec-sheet',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const listSpecSheets = vi.fn();
const queueSpecSheetPdf = vi.fn();
vi.mock('@/app/(protected)/project-sales/_shared/services/specSheetService', () => ({
  listSpecSheets: (...a: unknown[]) => listSpecSheets(...a),
  createSpecSheet: vi.fn(),
  getSpecSheet: vi.fn(),
  updateSpecSheet: vi.fn(),
  getSpecSheetPreview: vi.fn(),
  getSpecSheetPageDesign: vi.fn(),
  saveSpecSheetPageEdit: vi.fn(),
  queueSpecSheetPdf: (...a: unknown[]) => queueSpecSheetPdf(...a),
}));

const createPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...a: unknown[]) => createPendingAction(...a),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(async () => ({ pending: null, last_outcome: null })),
}));

let canEdit = true;
vi.mock('./QuotationDocumentContext', () => ({
  useQuotationDocumentScreen: () => ({ projectId: 'p1', documentId: 'd1', canEdit }),
}));

import { QuotationSpecSheetsList } from './QuotationSpecSheetsList';

const NO_DEFAULTS = {
  source: null,
  cover_template_id: null,
  page_template_id: null,
  single_page_template_id: null,
};

function row(over: Record<string, unknown>) {
  return {
    id: 'sheet-1',
    sheet_no: 1,
    label: 'SS1',
    source_label: 'PRJQ-2026-0027-R1',
    source_hint: 'issued 03 Nov 2026',
    is_draft: false,
    cover_name: 'Spec cover',
    page_name: 'Spec page',
    single_name: null,
    page_count: 5,
    edited_count: 0,
    created_by_name: 'Baser Ramli',
    created_at: '2026-11-03T03:00:00',
    updated_at: '2026-11-03T03:00:00',
    last_exported_at: null,
    newer_templates: false,
    ...over,
  };
}

function list(over: Record<string, unknown> = {}) {
  return {
    items: [],
    sources: [{ value: 'issue-1', label: 'PRJQ-2026-0027-R1', hint: 'issued 03 Nov 2026' }],
    templates: { cover: [], page: [] },
    defaults: NO_DEFAULTS,
    create_disabled_reason: null,
    ...over,
  };
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationSpecSheetsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  canEdit = true;
  push.mockReset();
  listSpecSheets.mockReset();
  queueSpecSheetPdf.mockReset().mockResolvedValue({});
  createPendingAction.mockReset().mockResolvedValue({
    id: 'pa-1',
    action_key: 'quotation_spec_sheet.delete',
    entity_type: 'quotation_spec_sheet',
    entity_id: 'sheet-2',
    commit_at: new Date(Date.now() + 10_000).toISOString().replace('Z', ''),
    window_seconds: 10,
  });
});

function openRowMenu(index = 0) {
  const triggers = screen.getAllByRole('button', { name: /actions/i });
  triggers[index].focus();
  fireEvent.keyDown(triggers[index], { key: 'ArrowDown', code: 'ArrowDown' });
}

describe('QuotationSpecSheetsList', () => {
  it('lists the spec sheets newest first with number, revision, templates, pages and edits', async () => {
    listSpecSheets.mockResolvedValue(
      list({
        items: [
          row({ id: 'sheet-2', sheet_no: 2, label: 'SS2', source_label: 'Draft after R1', is_draft: true, page_count: 7, edited_count: 2, page_name: 'Spec page B' }),
          row({}),
        ],
      }),
    );
    renderList();

    expect(await screen.findByText('SS2')).toBeInTheDocument();
    expect(screen.getByText('SS1')).toBeInTheDocument();
    expect(screen.getByText('Draft after R1')).toBeInTheDocument();
    expect(screen.getByText('PRJQ-2026-0027-R1')).toBeInTheDocument();
    // One line per cell: the page template is in the Templates tooltip, not a second line.
    expect(screen.getByTitle(/Spec page B/)).toBeInTheDocument();
    expect(screen.getByText(/2 edited/)).toBeInTheDocument();
    const order = screen.getAllByText(/^SS\d$/).map((el) => el.textContent);
    expect(order).toEqual(['SS2', 'SS1']);
    // No UUID reaches the screen.
    expect(document.body.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
    expect(listSpecSheets).toHaveBeenCalledTimes(1);
    expect(listSpecSheets).toHaveBeenCalledWith('p1', 'd1');
  });

  it('fits its card at 1280 (about 950 px) with no sideways scroll: the columns add up to 920 px or less', async () => {
    listSpecSheets.mockResolvedValue(list({ items: [row({})] }));
    renderList();
    await screen.findByText('SS1');
    // The grid's minimum width is the sum of its column sizes.
    const table = document.querySelector('[data-slot="data-grid-table"]') as HTMLElement;
    const minWidth = parseFloat(table.style.minWidth);
    expect(minWidth).toBeGreaterThan(0);
    expect(minWidth).toBeLessThanOrEqual(920);
  });

  it('the No. column is wide enough to show "SS1" whole (72 px or more)', async () => {
    listSpecSheets.mockResolvedValue(list({ items: [row({})] }));
    renderList();
    await screen.findByText('SS1');
    const th = screen.getByRole('columnheader', { name: /No\./ }) as HTMLElement;
    expect(parseFloat(th.style.width)).toBeGreaterThanOrEqual(72);
  });

  it('opens the sheet when its row is clicked', async () => {
    listSpecSheets.mockResolvedValue(list({ items: [row({})] }));
    renderList();

    fireEvent.click(await screen.findByText('SS1'));

    expect(push).toHaveBeenCalledTimes(1);
    expect(push.mock.calls[0][0]).toContain(
      '/project-sales/p1/quotation-documents/d1/spec-sheet/sheet-1',
    );
  });

  it('shows the empty state with a heading and no button in the body, and the one CTA in the header', async () => {
    listSpecSheets.mockResolvedValue(list());
    renderList();

    expect(await screen.findByText('No spec sheets yet')).toBeInTheDocument();
    const cta = screen.getByRole('button', { name: 'Create spec sheet' });
    expect(cta).toBeEnabled();
    expect(screen.getAllByRole('button', { name: /create spec sheet/i })).toHaveLength(1);
  });

  it('disables Create with the reason when the quotation has no line', async () => {
    listSpecSheets.mockResolvedValue(
      list({ sources: [], create_disabled_reason: 'Add a line to the quotation first.' }),
    );
    renderList();

    expect(await screen.findByText('No lines yet')).toBeInTheDocument();
    const cta = screen.getByRole('button', { name: 'Create spec sheet' });
    expect(cta).toBeDisabled();
    expect(cta).toHaveAttribute('title', 'Add a line to the quotation first.');
  });

  it('shows a load error instead of an empty state when the list cannot be read', async () => {
    listSpecSheets.mockRejectedValue(new Error('Could not load the spec sheets'));
    renderList();

    expect(await screen.findByText(/Could not load the spec sheets/)).toBeInTheDocument();
    expect(screen.queryByText('No spec sheets yet')).toBeNull();
  });

  it('Delete starts the deferred countdown: no confirm dialog, the server is asked to park it', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    listSpecSheets.mockResolvedValue(
      list({ items: [row({ id: 'sheet-2', sheet_no: 2, label: 'SS2' }), row({})] }),
    );
    renderList();
    await screen.findByText('SS2');

    openRowMenu(0);
    fireEvent.click(await screen.findByRole('menuitem', { name: /delete/i }));

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(1));
    expect(createPendingAction).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'quotation_spec_sheet.delete',
        entityType: 'quotation_spec_sheet',
        entityId: 'sheet-2',
      }),
    );
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
    confirm.mockRestore();
  });

  it('Export PDF from the row menu queues the sheet', async () => {
    listSpecSheets.mockResolvedValue(list({ items: [row({})] }));
    renderList();
    await screen.findByText('SS1');

    openRowMenu(0);
    fireEvent.click(await screen.findByRole('menuitem', { name: /export pdf/i }));

    await waitFor(() => expect(queueSpecSheetPdf).toHaveBeenCalledWith('p1', 'd1', 'sheet-1'));
  });

  it('a reader without the edit right gets no Create and no Delete, but keeps View and Export PDF', async () => {
    canEdit = false;
    listSpecSheets.mockResolvedValue(list({ items: [row({})] }));
    renderList();
    await screen.findByText('SS1');

    expect(screen.queryByRole('button', { name: 'Create spec sheet' })).toBeNull();
    openRowMenu(0);
    expect(await screen.findByRole('menuitem', { name: /export pdf/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /view/i })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /delete/i })).toBeNull();
  });

  it('renders every row as one line: no second-line element, long values carry a title', async () => {
    listSpecSheets.mockResolvedValue(
      list({
        items: [
          row({
            id: 'sheet-2',
            sheet_no: 2,
            label: 'SS2',
            source_label: 'Draft after A',
            source_hint: 'lines taken 03 Nov 2026 16:10',
            is_draft: true,
            edited_count: 2,
            single_name: 'Single item',
            last_exported_at: '2026-11-03T04:00:00',
          }),
        ],
      }),
    );
    renderList();
    await screen.findByText('SS2');

    const cells = Array.from(document.querySelectorAll('[role="row"] [role="cell"], tbody td'));
    expect(cells.length).toBeGreaterThan(5);
    for (const cell of cells) {
      // A cell holds inline content only: no block child, no stacked sub line.
      expect(cell.querySelector('.block.text-xs, .sub, p, br')).toBeNull();
    }
    // The old second lines are gone.
    expect(screen.queryByText(/lines taken/)).toBeNull();
    expect(screen.queryByText(/issued 03 Nov/)).toBeNull();
    expect(screen.queryByText(/no PDF yet/)).toBeNull();
    expect(screen.queryByText(/PDF 0?3/)).toBeNull();
    // Templates: the cover name in the cell, all three in the tooltip.
    expect(screen.getByTitle('Spec cover / Spec page / Single item')).toHaveTextContent(/^Spec cover$/);
    // Revision label only, with its tooltip; the creator and the two dates each in their own cell.
    expect(screen.getByTitle('Draft after A')).toHaveTextContent(/^Draft after A$/);
    expect(screen.getByTitle('Baser Ramli')).toBeInTheDocument();
    expect(screen.getByText(/2 edited/)).toBeInTheDocument();
  });
});
