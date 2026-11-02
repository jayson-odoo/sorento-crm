/**
 * PS-SPEC-SHEET: the Spec sheet tab of a quotation document.
 *
 * What is pinned: the two empty states (no revision, no templates), Export stays off until a
 * revision and both templates are set (with the reason as its title), every page row shows, and
 * switching a page's Print off saves the rows with that page hidden, keyed by item.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { SpecSheetView } from '../../../../_shared/services/specSheetService';

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
    disconnect() {}
  };
}

const getSpecSheet = vi.fn();
const saveSpecSheet = vi.fn();
const getSpecSheetPreview = vi.fn();
const queueSpecSheetPdf = vi.fn();

vi.mock('../../../../_shared/services/specSheetService', () => ({
  getSpecSheet: (...a: unknown[]) => getSpecSheet(...a),
  saveSpecSheet: (...a: unknown[]) => saveSpecSheet(...a),
  getSpecSheetPreview: (...a: unknown[]) => getSpecSheetPreview(...a),
  queueSpecSheetPdf: (...a: unknown[]) => queueSpecSheetPdf(...a),
}));

vi.mock('@/components/dealer-kit/ScaledSheet', () => ({
  default: ({ sheetIndex }: { sheetIndex: number }) => <div data-testid={`sheet-${sheetIndex}`} />,
  sheetPixelSize: () => ({ width: 1280, height: 720 }),
}));

let canEdit = true;
vi.mock('./QuotationDocumentContext', () => ({
  useQuotationDocumentScreen: () => ({ projectId: 'p1', documentId: 'd1', canEdit }),
}));

import { QuotationSpecSheetTab } from './QuotationSpecSheetTab';

function view(over: Partial<SpecSheetView> = {}): SpecSheetView {
  return {
    settings: {
      cover_template_id: 'cover-1',
      page_template_id: 'page-1',
      single_page_template_id: null,
      issue_id: null,
      rows: [],
    },
    issue_id: 'issue-1',
    issues: [{ id: 'issue-1', issue_no: 1, label: 'SRT/Q/2026/0141 (R1)', issued_at: null }],
    pages: [
      {
        key: 'prod-basin',
        line_id: 'l1',
        product_id: 'prod-basin',
        code: 'SRTWB0002',
        name: 'Counter top basin',
        brand: 'SORENTO',
        image_attachment_id: null,
        drawing_attachment_id: null,
        accessories: [],
        picked: [],
        area: 'UNIT',
        comment: '',
        marker: '',
        hidden: false,
      },
      {
        key: 'set:wc',
        line_id: 'l2',
        product_id: 'prod-wc',
        code: 'SRTWC0001-RL',
        name: 'Wall hung WC',
        brand: 'SORENTO',
        image_attachment_id: null,
        drawing_attachment_id: null,
        accessories: [
          { key: null, source: 'set', product_id: 'av', code: 'SRTAV0010', name: 'Angle valve', brand: '' },
        ],
        picked: [],
        area: '',
        comment: '',
        marker: '*',
        hidden: false,
      },
    ],
    templates: {
      cover: [{ id: 'cover-1', name: 'Catalogue cover', width_mm: 338.7, height_mm: 190.5 }],
      page: [{ id: 'page-1', name: 'Item with accessories', width_mm: 338.7, height_mm: 190.5 }],
    },
    ...over,
  };
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <QuotationSpecSheetTab />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  canEdit = true;
  getSpecSheet.mockReset();
  saveSpecSheet.mockReset();
  getSpecSheetPreview.mockReset();
  queueSpecSheetPdf.mockReset();
  getSpecSheetPreview.mockResolvedValue({
    doc: { kind: 'tag_sheet', imposition: { page_width_mm: 338.7, page_height_mm: 190.5 }, sheets: [{}, {}, {}] },
    resolvedData: {},
    assets: {},
    images: {},
    fonts: [],
    version: 1,
    page_size: { width_mm: 338.7, height_mm: 190.5 },
  });
});

describe('Spec sheet tab', () => {
  it('lists every page in print order after the cover and previews them', async () => {
    getSpecSheet.mockResolvedValue(view());
    renderTab();

    expect(await screen.findByTestId('spec-sheet-page-SRTWB0002')).toHaveTextContent('p. 2');
    expect(screen.getByTestId('spec-sheet-page-SRTWC0001-RL')).toHaveTextContent('p. 3');
    expect(screen.getByTestId('spec-sheet-page-SRTWC0001-RL')).toHaveTextContent('With SRTAV0010');
    expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();
    expect(screen.getByTestId('spec-sheet-export')).toBeEnabled();
  });

  it('says to issue a revision first, with Export off', async () => {
    getSpecSheet.mockResolvedValue(view({ issue_id: null, issues: [], pages: [] }));
    renderTab();

    expect(await screen.findByText('No issued revision yet')).toBeInTheDocument();
    const exportButton = screen.getByTestId('spec-sheet-export');
    expect(exportButton).toBeDisabled();
    expect(exportButton).toHaveAttribute('title', 'Issue a revision first.');
    expect(getSpecSheetPreview).not.toHaveBeenCalled();
  });

  it('says where to publish templates, and Export waits for both picks', async () => {
    getSpecSheet.mockResolvedValue(
      view({
        settings: { ...view().settings, cover_template_id: null, page_template_id: null },
        templates: { cover: [], page: [] },
      }),
    );
    renderTab();

    expect(await screen.findByText('No spec sheet templates')).toBeInTheDocument();
    expect(screen.getByTestId('spec-sheet-export')).toHaveAttribute(
      'title',
      'Pick a cover template and a page template first.',
    );
  });

  it('switching Print off saves the rows with that page hidden, keyed by item', async () => {
    getSpecSheet.mockResolvedValue(view());
    saveSpecSheet.mockResolvedValue(view());
    renderTab();

    fireEvent.click(await screen.findByRole('switch', { name: 'Print SRTWB0002' }));

    await waitFor(() => expect(saveSpecSheet).toHaveBeenCalled());
    const [, , body] = saveSpecSheet.mock.calls[0];
    expect(body.rows).toEqual([
      { key: 'prod-basin', area: 'UNIT', comment: '', marker: '', hidden: true, accessories: [] },
      { key: 'set:wc', area: '', comment: '', marker: '*', hidden: false, accessories: [] },
    ]);
  });

  it('Export PDF queues the chosen revision', async () => {
    getSpecSheet.mockResolvedValue(view());
    queueSpecSheetPdf.mockResolvedValue({ id: 'dl1' });
    renderTab();

    fireEvent.click(await screen.findByTestId('spec-sheet-export'));
    await waitFor(() => expect(queueSpecSheetPdf).toHaveBeenCalledWith('p1', 'd1', 'issue-1'));
  });

  it('a reader without the edit right sees the pages but cannot change them', async () => {
    canEdit = false;
    getSpecSheet.mockResolvedValue(view());
    renderTab();

    expect(await screen.findByRole('switch', { name: 'Print SRTWB0002' })).toBeDisabled();
    expect(screen.queryByLabelText('Drag SRTWB0002 to reorder')).toBeNull();
  });
});
