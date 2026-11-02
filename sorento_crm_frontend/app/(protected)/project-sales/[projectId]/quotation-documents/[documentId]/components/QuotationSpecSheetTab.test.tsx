/**
 * PS-SPEC-SHEET: the Spec sheet tab of a quotation document, canvas flow (owner, mock v5).
 *
 * Pinned: the empty states and Export gating; a strip of pages (cover first, printed pages
 * numbered); the open page's AREA spot types over the Section heading and saves upper case,
 * keyed by item, while an untouched AREA is never saved as typed; Leave out / Put back; Add
 * accessory offers other items only; a reader without the edit right gets no actions.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

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

// jsdom lays nothing out; the open page needs a width to place its edit spots.
const clientWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth');
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, get: () => 1280 });
});
afterAll(() => {
  if (clientWidth) Object.defineProperty(HTMLElement.prototype, 'clientWidth', clientWidth);
});

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
  PX_PER_MM: 96 / 25.4,
}));

let canEdit = true;
vi.mock('./QuotationDocumentContext', () => ({
  useQuotationDocumentScreen: () => ({ projectId: 'p1', documentId: 'd1', canEdit }),
}));

import { QuotationSpecSheetTab } from './QuotationSpecSheetTab';

function page(key: string, code: string, name: string, over = {}) {
  return {
    key,
    line_id: `l-${key}`,
    product_id: key,
    code,
    name,
    brand: 'SORENTO',
    image_attachment_id: null,
    drawing_attachment_id: null,
    accessories: [],
    picked: [],
    area: 'UNIT',
    area_default: 'UNIT',
    comment: '',
    marker: '',
    hidden: false,
    ...over,
  };
}

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
    issues: [{ id: 'issue-1', issue_no: 1, label: 'SRT/Q/2026/0141-R1', issued_at: null }],
    pages: [
      page('set:wc', 'SRTWC0001-RL', 'Wall hung WC', {
        accessories: [
          { key: null, source: 'set', product_id: 'av', code: 'SRTAV0010', name: 'Angle valve', brand: '' },
        ],
      }),
      page('basin', 'SRTWB0002', 'Counter top basin'),
      page('trap', 'SRTBT0006', 'Bottle trap', { area: '', area_default: '' }),
    ],
    templates: {
      cover: [{ id: 'cover-1', name: 'Catalogue cover', width_mm: 338.7, height_mm: 190.5 }],
      page: [{ id: 'page-1', name: 'Item with accessories', width_mm: 338.7, height_mm: 190.5 }],
    },
    ...over,
  } as SpecSheetView;
}

const textLayer = (id: string, text: string, y: number) => ({
  id,
  type: 'text',
  x_mm: 260,
  y_mm: y,
  width_mm: 70,
  height_mm: 8,
  rotation_deg: 0,
  z_index: 1,
  locked: false,
  visible: true,
  slot_binding: null,
  text_override: null,
  props: {
    kind: 'text',
    text,
    fontFamily: 'Arial',
    fontSize: 7,
    fontWeight: 700,
    color: '#000',
    align: 'left',
    lineHeight: 1.2,
    letterSpacing: 0,
  },
});

function sheet(key: string) {
  return {
    id: `sheet-${key}`,
    tags: [
      {
        id: `tag-${key}`,
        template_id: 't',
        request_tag_id: key,
        x_mm: 0,
        y_mm: 0,
        width_mm: 338.7,
        height_mm: 190.5,
        layers:
          key === 'cover'
            ? []
            : [
                textLayer('area', 'AREA : {{line.area}}', 110),
                textLayer('comment', 'COMMENT : {{ line.comment }}', 130),
              ],
      },
    ],
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
  for (const fn of [getSpecSheet, saveSpecSheet, getSpecSheetPreview, queueSpecSheetPdf]) {
    fn.mockReset();
  }
  getSpecSheetPreview.mockResolvedValue({
    doc: {
      kind: 'tag_sheet',
      imposition: {
        preset: 'custom',
        page_width_mm: 338.7,
        page_height_mm: 190.5,
        bleed_mm: 0,
        gap_mm: 0,
      },
      sheets: ['cover', 'set:wc', 'basin', 'trap'].map(sheet),
    },
    resolvedData: {},
    assets: {},
    images: {},
    fonts: [],
    version: 1,
    page_size: { width_mm: 338.7, height_mm: 190.5 },
  });
});

async function openPage(code: string) {
  const strip = await screen.findByTestId('spec-sheet-strip');
  fireEvent.click(
    within(strip).getByRole('button', { name: new RegExp(`^\\S+ ${code}$`), pressed: false }),
  );
}

describe('Spec sheet tab (canvas flow)', () => {
  it('shows a strip of the pages, the cover first, printed pages numbered, and no table', async () => {
    getSpecSheet.mockResolvedValue(view());
    renderTab();

    const strip = await screen.findByTestId('spec-sheet-strip');
    for (const label of ['1 Cover', '2 SRTWC0001-RL', '3 SRTWB0002', '4 SRTBT0006']) {
      expect(within(strip).getByRole('button', { name: label })).toBeInTheDocument();
    }
    expect(screen.getByTestId('spec-sheet-open-page')).toHaveTextContent('Page 1: Cover');
    expect(screen.getByTestId('spec-sheet-export')).toBeEnabled();
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('says to issue a revision first, with Export off and no pages drawn', async () => {
    getSpecSheet.mockResolvedValue(view({ issue_id: null, issues: [], pages: [] }));
    renderTab();

    expect(await screen.findByText('No issued revision yet')).toBeInTheDocument();
    expect(screen.getByTestId('spec-sheet-export')).toBeDisabled();
    expect(screen.getByTestId('spec-sheet-export-reason')).toHaveAttribute(
      'title',
      'Issue a revision first.',
    );
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
    expect(screen.getByTestId('spec-sheet-export-reason')).toHaveAttribute(
      'title',
      'Pick a cover template and a page template first.',
    );
  });

  it('typing AREA on the page saves it upper case; an untouched Section heading is not saved as typed', async () => {
    getSpecSheet.mockResolvedValue(view());
    saveSpecSheet.mockResolvedValue(view());
    renderTab();

    await openPage('SRTWB0002');
    expect(screen.getByTestId('spec-sheet-open-page')).toHaveTextContent('Page 3: SRTWB0002');
    fireEvent.click(screen.getByRole('button', { name: 'Edit Area' }));
    const input = screen.getByRole('textbox', { name: 'Area' });
    expect(input).toHaveValue('UNIT');
    fireEvent.change(input, { target: { value: 'pantry (type a)' } });
    fireEvent.blur(input);

    await waitFor(() => expect(saveSpecSheet).toHaveBeenCalled());
    expect(saveSpecSheet.mock.calls[0][2].rows).toEqual([
      { key: 'set:wc', area: '', comment: '', marker: '', hidden: false, accessories: [] },
      { key: 'basin', area: 'PANTRY (TYPE A)', comment: '', marker: '', hidden: false, accessories: [] },
      { key: 'trap', area: '', comment: '', marker: '', hidden: false, accessories: [] },
    ]);
  });

  it('typing COMMENT on the page saves it as typed', async () => {
    getSpecSheet.mockResolvedValue(view());
    saveSpecSheet.mockResolvedValue(view());
    renderTab();

    await openPage('SRTWC0001-RL');
    fireEvent.click(screen.getByRole('button', { name: 'Edit Comment' }));
    const input = screen.getByRole('textbox', { name: 'Comment' });
    fireEvent.change(input, { target: { value: 'Soft close seat' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(saveSpecSheet).toHaveBeenCalled());
    expect(saveSpecSheet.mock.calls[0][2].rows[0]).toMatchObject({
      key: 'set:wc',
      comment: 'Soft close seat',
    });
  });

  it('Leave out saves the page hidden, keyed by item', async () => {
    getSpecSheet.mockResolvedValue(view());
    saveSpecSheet.mockResolvedValue(view());
    renderTab();

    await openPage('SRTBT0006');
    fireEvent.click(screen.getByTestId('spec-sheet-leave-out'));

    await waitFor(() => expect(saveSpecSheet).toHaveBeenCalled());
    expect(saveSpecSheet.mock.calls[0][2].rows[2]).toEqual({
      key: 'trap',
      area: '',
      comment: '',
      marker: '',
      hidden: true,
      accessories: [],
    });
  });

  it('a left-out page says so and offers Put back', async () => {
    const base = view();
    getSpecSheet.mockResolvedValue(
      view({ pages: [base.pages[0], { ...base.pages[1], hidden: true }] }),
    );
    renderTab();

    await openPage('SRTWB0002');
    expect(screen.getByText('Left out of the spec sheet')).toBeInTheDocument();
    expect(screen.getByTestId('spec-sheet-leave-out')).toHaveTextContent('Put back');
  });

  it('Add accessory offers the other items, never the open page itself', async () => {
    getSpecSheet.mockResolvedValue(view());
    renderTab();

    await openPage('SRTWB0002');
    fireEvent.click(screen.getByRole('combobox', { name: /Add accessory/i }));
    expect(await screen.findByRole('option', { name: /SRTBT0006/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /SRTWC0001-RL/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /SRTWB0002/ })).toBeNull();
  });

  it('Export PDF queues the chosen revision', async () => {
    getSpecSheet.mockResolvedValue(view());
    queueSpecSheetPdf.mockResolvedValue({ id: 'dl1' });
    renderTab();

    fireEvent.click(await screen.findByTestId('spec-sheet-export'));
    await waitFor(() => expect(queueSpecSheetPdf).toHaveBeenCalledWith('p1', 'd1', 'issue-1'));
  });

  it('a reader without the edit right sees the pages but no edit spots, actions or drag', async () => {
    canEdit = false;
    getSpecSheet.mockResolvedValue(view());
    renderTab();

    await openPage('SRTWB0002');
    expect(screen.queryByRole('button', { name: 'Edit Area' })).toBeNull();
    expect(screen.queryByTestId('spec-sheet-leave-out')).toBeNull();
    expect(screen.queryByLabelText('Drag SRTWB0002 to reorder')).toBeNull();
  });
});
