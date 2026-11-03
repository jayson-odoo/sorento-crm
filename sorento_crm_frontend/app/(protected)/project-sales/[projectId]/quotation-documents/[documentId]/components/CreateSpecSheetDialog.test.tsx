/**
 * SPEC-SHEET-V2 red test 17: the Create spec sheet dialog.
 *
 * Written BEFORE the component. Contract of this file:
 *
 *   Component   `CreateSpecSheetDialog` (named export of ./CreateSpecSheetDialog), props
 *               `{ open, onOpenChange, projectId, documentId }`. Built on `FormDialogScaffold`; it reads
 *               the options and defaults from the list query (`listSpecSheets`), no other fetch.
 *   Fields      four `SearchableSelect`s with ids `spec-sheet-source`, `spec-sheet-cover`,
 *               `spec-sheet-page`, `spec-sheet-single`; only the Single one is `clearable`. Single
 *               options are the page templates. Source options keep the server order (draft first).
 *   Submit      `createSpecSheet(projectId, documentId, { source, cover_template_id,
 *               page_template_id, single_page_template_id })` (single is null when cleared), then
 *               `router.push('/project-sales/<p>/quotation-documents/<d>/spec-sheet/<new id>')`.
 *   Service     `@/app/(protected)/project-sales/_shared/services/specSheetService` exports exactly:
 *                 listSpecSheets, createSpecSheet, getSpecSheet, updateSpecSheet, getSpecSheetPreview,
 *                 getSpecSheetPageDesign, saveSpecSheetPageEdit, queueSpecSheetPdf
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

const listSpecSheets = vi.fn();
const createSpecSheet = vi.fn();
const updateSpecSheet = vi.fn();
vi.mock('@/app/(protected)/project-sales/_shared/services/specSheetService', () => ({
  listSpecSheets: (...a: unknown[]) => listSpecSheets(...a),
  createSpecSheet: (...a: unknown[]) => createSpecSheet(...a),
  getSpecSheet: vi.fn(),
  updateSpecSheet: (...a: unknown[]) => updateSpecSheet(...a),
  getSpecSheetPreview: vi.fn(),
  getSpecSheetPageDesign: vi.fn(),
  saveSpecSheetPageEdit: vi.fn(),
  queueSpecSheetPdf: vi.fn(),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
    clearable,
  }: {
    id?: string;
    value: string | null;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    clearable?: boolean;
  }) => (
    <div>
      <select
        id={id}
        data-testid={id}
        data-clearable={clearable ? 'true' : 'false'}
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">-</option>
        {(options ?? []).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {clearable && value ? (
        <button type="button" aria-label={`Clear ${id}`} onClick={() => onChange('')} />
      ) : null}
    </div>
  ),
}));

import { CreateSpecSheetDialog } from './CreateSpecSheetDialog';

const LIST = {
  items: [],
  sources: [
    { value: 'draft', label: 'Current draft', hint: 'changed after R2 · not issued' },
    { value: 'issue-2', label: 'PRJQ-2026-0027-R2', hint: 'issued 03 Nov 2026' },
    { value: 'issue-1', label: 'PRJQ-2026-0027-R1', hint: 'issued 02 Nov 2026' },
  ],
  templates: {
    cover: [{ id: 'cover-1', name: 'Spec cover', width_mm: 338.7, height_mm: 190.5 }],
    page: [
      { id: 'page-1', name: 'With accessories', width_mm: 338.7, height_mm: 190.5 },
      { id: 'page-2', name: 'Single item', width_mm: 338.7, height_mm: 190.5 },
    ],
  },
  defaults: {
    source: 'draft',
    cover_template_id: 'cover-1',
    page_template_id: 'page-1',
    single_page_template_id: 'page-2',
  },
  create_disabled_reason: null,
};

function renderDialog(onOpenChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CreateSpecSheetDialog open onOpenChange={onOpenChange} projectId="p1" documentId="d1" />
    </QueryClientProvider>,
  );
  return onOpenChange;
}

const options = (id: string) =>
  within(screen.getByTestId(id))
    .getAllByRole('option')
    .map((o) => (o as HTMLOptionElement).value)
    .filter(Boolean);

beforeEach(() => {
  push.mockReset();
  listSpecSheets.mockReset().mockResolvedValue(LIST);
  createSpecSheet.mockReset().mockResolvedValue({ id: 'sheet-9', label: 'SS3' });
  updateSpecSheet.mockReset().mockResolvedValue({ id: 'sheet-5', label: 'SS1' });
});

describe('CreateSpecSheetDialog', () => {
  it('offers the draft first, then every revision newest first, and no signature is asked for', async () => {
    renderDialog();

    await screen.findByTestId('spec-sheet-source');
    await waitFor(() => expect(options('spec-sheet-source')).toHaveLength(3));
    expect(options('spec-sheet-source')).toEqual(['draft', 'issue-2', 'issue-1']);
    expect(screen.queryByText(/sign/i)).toBeNull();
    // Cover templates are cover templates; the page and single pickers offer the page templates.
    expect(options('spec-sheet-cover')).toEqual(['cover-1']);
    expect(options('spec-sheet-page')).toEqual(['page-1', 'page-2']);
    expect(options('spec-sheet-single')).toEqual(['page-1', 'page-2']);
  });

  it('only the Single item template is clearable', async () => {
    renderDialog();
    await waitFor(() => expect(options('spec-sheet-source')).toHaveLength(3));

    expect(screen.getByTestId('spec-sheet-single')).toHaveAttribute('data-clearable', 'true');
    for (const id of ['spec-sheet-source', 'spec-sheet-cover', 'spec-sheet-page']) {
      expect(screen.getByTestId(id)).toHaveAttribute('data-clearable', 'false');
    }
  });

  it('starts from the server defaults', async () => {
    renderDialog();
    await waitFor(() => expect(options('spec-sheet-source')).toHaveLength(3));

    await waitFor(() => expect(screen.getByTestId('spec-sheet-source')).toHaveValue('draft'));
    expect(screen.getByTestId('spec-sheet-cover')).toHaveValue('cover-1');
    expect(screen.getByTestId('spec-sheet-page')).toHaveValue('page-1');
    expect(screen.getByTestId('spec-sheet-single')).toHaveValue('page-2');
  });

  it('submits the picked revision and templates, then opens the new sheet', async () => {
    const onOpenChange = renderDialog();
    await waitFor(() => expect(options('spec-sheet-source')).toHaveLength(3));
    await waitFor(() => expect(screen.getByTestId('spec-sheet-source')).toHaveValue('draft'));

    fireEvent.change(screen.getByTestId('spec-sheet-source'), { target: { value: 'issue-2' } });
    fireEvent.click(screen.getByLabelText('Clear spec-sheet-single'));
    fireEvent.click(screen.getByRole('button', { name: /^create/i }));

    await waitFor(() => expect(createSpecSheet).toHaveBeenCalledTimes(1));
    expect(createSpecSheet).toHaveBeenCalledWith('p1', 'd1', {
      source: 'issue-2',
      cover_template_id: 'cover-1',
      page_template_id: 'page-1',
      single_page_template_id: null,
    });
    await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
    expect(push.mock.calls[0][0]).toContain(
      '/project-sales/p1/quotation-documents/d1/spec-sheet/sheet-9',
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows the server refusal inside the dialog and stays put', async () => {
    createSpecSheet.mockRejectedValue(new Error('Page templates must be the same size as the cover.'));
    renderDialog();
    await waitFor(() => expect(screen.getByTestId('spec-sheet-source')).toHaveValue('draft'));

    fireEvent.click(screen.getByRole('button', { name: /^create/i }));

    expect(
      await screen.findByText('Page templates must be the same size as the cover.'),
    ).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it('in templates mode hides the revision, prefills the sheet templates and saves them on that sheet', async () => {
    const onOpenChange = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <CreateSpecSheetDialog
          open
          onOpenChange={onOpenChange}
          projectId="p1"
          documentId="d1"
          sheet={{ id: 'sheet-5', cover: null, page: 'page-2', single: null }}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(options('spec-sheet-cover')).toEqual(['cover-1']));
    expect(screen.queryByTestId('spec-sheet-source')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Pick templates' })).toBeInTheDocument();
    // The deleted cover falls back to the default, the sheet's own page template stays.
    await waitFor(() => expect(screen.getByTestId('spec-sheet-cover')).toHaveValue('cover-1'));
    expect(screen.getByTestId('spec-sheet-page')).toHaveValue('page-2');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updateSpecSheet).toHaveBeenCalledTimes(1));
    expect(updateSpecSheet).toHaveBeenCalledWith('p1', 'd1', 'sheet-5', {
      cover_template_id: 'cover-1',
      page_template_id: 'page-2',
      single_page_template_id: null,
    });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(createSpecSheet).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });
});
