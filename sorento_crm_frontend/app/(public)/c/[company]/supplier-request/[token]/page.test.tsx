/**
 * F8 / S4 - what the supplier sees when they open the link (AC-C6, AC-C7, AC-D5).
 *
 * The page is THEIR sheet now, not a listing of ours: their ten columns in their own
 * spellings, their merged families as `rowSpan`, their yellow fields and red figures, and
 * their `合计` row, with our English labels as a second header line and column K appended.
 *
 * The properties worth a test are still the ones about what is NOT on the page - a stranger
 * holding the URL must not read a price, and a dead link must not say WHY it is dead - plus
 * the ones that make the sheet theirs rather than ours.
 *
 * The service is mocked at the module boundary; nothing hits the network.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';

import PublicSupplierRequestPage from './page';
import type {
  SupplierRequest,
  SupplierRequestSheetCell,
} from '../../../lib/publicSupplierRequestService';

const readSupplierRequest = vi.fn();
const readSupplierRequestDocument = vi.fn();

class Unavailable extends Error {}

vi.mock('../../../lib/publicSupplierRequestService', () => ({
  readSupplierRequest: (...args: unknown[]) => readSupplierRequest(...args),
  readSupplierRequestDocument: (...args: unknown[]) => readSupplierRequestDocument(...args),
  SupplierRequestUnavailableError: class extends Error {},
}));

function cell(
  value: string | number | null,
  extra: Partial<SupplierRequestSheetCell> = {},
): SupplierRequestSheetCell {
  return { value, rowspan: 1, colspan: 1, covered: false, fill: null, red: false, ...extra };
}

const REQUEST: SupplierRequest = {
  supplier_name: 'CHAOZHOU JINBAICHUAN SANITARY WARE TECHNOLOGY CO., LTD',
  requested_at: '2026-07-31T02:00:00',
  line_count: 2,
  sheet: {
    title: '金百川库存表 2026年7月27日',
    columns: [
      { label: '序号', label_en: 'No.' },
      { label: '型号', label_en: 'Model' },
      { label: '品名', label_en: 'Description' },
      { label: '包装好库存', label_en: 'Packed' },
      { label: '空瓷', label_en: 'Unfinished' },
      { label: '总体积(cbm)', label_en: 'Total CBM' },
      { label: '需装数量', label_en: 'Qty to load' },
    ],
    rows: [
      {
        // One 序号 and one volume over two rows, exactly as their file merges them.
        cells: [
          cell(1, { rowspan: 2 }),
          cell('SRTWB241', { fill: 'yellow' }),
          cell('Basin 600mm', { fill: 'yellow' }),
          cell(0, { fill: 'yellow', red: true }),
          cell(340, { fill: 'yellow' }),
          cell(12.5, { rowspan: 2 }),
          cell(500),
        ],
        family_span: 2,
        appended: false,
      },
      {
        cells: [
          cell(null, { covered: true }),
          cell('SRTWB243', { fill: 'yellow' }),
          cell('Basin 800mm', { fill: 'yellow' }),
          cell(120, { fill: 'yellow' }),
          cell(null, { fill: 'yellow' }),
          cell(null, { covered: true }),
          cell(80),
        ],
        family_span: 0,
        appended: false,
      },
    ],
    totals: {
      cells: [
        cell('合计：', { colspan: 3 }),
        cell(null, { covered: true }),
        cell(null, { covered: true }),
        cell(120),
        cell(340),
        cell(12.5),
        cell(580),
      ],
      family_span: 0,
      appended: false,
    },
  },
  lines: [
    {
      item_code: 'SRTWB241',
      product_name: 'Basin 600mm',
      qty: 500,
      qty_packed: 120,
      qty_unfinished: 340,
    },
    {
      item_code: 'SRTWB243',
      product_name: 'Basin 800mm',
      qty: 80,
      qty_packed: null,
      qty_unfinished: null,
    },
  ],
  has_pdf: true,
  has_xlsx: true,
};

/**
 * The page resolves its route params with `use(params)`, which suspends on the first pass,
 * so the render has to be flushed inside `act` before anything can be asserted - the same
 * shape `warehouses/[id]/page.test.tsx` uses.
 */
async function renderPage() {
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <Suspense fallback={null}>
        <PublicSupplierRequestPage
          params={Promise.resolve({ company: 'SRT', token: 'tok-1' })}
        />
      </Suspense>,
    );
  });
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  readSupplierRequest.mockResolvedValue(REQUEST);
});

describe('the supplier request page', () => {
  it('names the supplier, the date and every line', async () => {
    await renderPage();

    await waitFor(() => expect(screen.getByText(REQUEST.supplier_name)).toBeInTheDocument());
    expect(screen.getByText(/31\/07\/2026/)).toBeInTheDocument();
    expect(screen.getByText('SRTWB241')).toBeInTheDocument();
    expect(screen.getByText('SRTWB243')).toBeInTheDocument();
    expect(screen.getByText('500')).toBeInTheDocument();
    expect(screen.getByText('80')).toBeInTheDocument();
  });

  it('writes their heading with ours as a second line', async () => {
    // AC-D5. Their spellings stay theirs; the English sits under them so our own people can
    // check what went out without renaming a single column of the supplier's.
    await renderPage();

    await waitFor(() => expect(screen.getByText(/配柜要求/)).toBeInTheDocument());
    expect(screen.getByText('型号')).toBeInTheDocument();
    expect(screen.getByText('Model')).toBeInTheDocument();
    expect(screen.getByText('需装数量')).toBeInTheDocument();
    expect(screen.getByText('Qty to load')).toBeInTheDocument();
    expect(screen.getByText('金百川库存表 2026年7月27日')).toBeInTheDocument();
  });

  it('merges a family the way their sheet does', async () => {
    // AC-D5. `rowSpan`, not a repeated value: printing the volume once per row would read as
    // that many times the volume.
    const { container } = await renderPage();

    await waitFor(() => expect(screen.getByText('SRTWB241')).toBeInTheDocument());
    const spanned = container.querySelectorAll('td[rowspan="2"]');
    expect(spanned.length).toBe(2);
    expect(container.querySelectorAll('tbody tr')[1]?.querySelectorAll('td').length).toBe(5);
  });

  it('keeps their yellow fields, their red figures and their total row', async () => {
    const { container } = await renderPage();

    await waitFor(() => expect(screen.getByText('SRTWB241')).toBeInTheDocument());
    expect(container.querySelectorAll('td.bg-\\[\\#ffff00\\]').length).toBeGreaterThan(0);
    expect(container.querySelector('td.text-red-600')).not.toBeNull();
    expect(screen.getByText('合计：')).toBeInTheDocument();
    expect(screen.getByText('580')).toBeInTheDocument();
  });

  it('shows their own figures, and leaves a cell they never filled empty', async () => {
    const { container } = await renderPage();

    await waitFor(() => expect(screen.getAllByText('340').length).toBe(2));
    expect(screen.getAllByText('120').length).toBe(2);
    const blanks = Array.from(container.querySelectorAll('tbody td')).filter(
      (td) => td.textContent === '',
    );
    expect(blanks.length).toBeGreaterThanOrEqual(1);
  });

  it('says the request is empty rather than drawing an empty sheet', async () => {
    readSupplierRequest.mockResolvedValue({ ...REQUEST, sheet: null, lines: [] });
    await renderPage();

    await waitFor(() =>
      expect(screen.getByText(/This request has no items/)).toBeInTheDocument(),
    );
  });

  it('offers both downloads', async () => {
    await renderPage();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /pdf/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: /excel/i })).toBeInTheDocument();
  });

  it('offers no download the request does not carry', async () => {
    readSupplierRequest.mockResolvedValue({ ...REQUEST, has_xlsx: false });
    await renderPage();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /pdf/i })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('button', { name: /excel/i })).not.toBeInTheDocument();
  });

  it('states no price and no cost anywhere', async () => {
    const { container } = await renderPage();

    await waitFor(() => expect(screen.getByText('SRTWB241')).toBeInTheDocument());
    const text = (container.textContent ?? '').toLowerCase();
    expect(text).not.toContain('price');
    expect(text).not.toContain('cost');
    expect(text).not.toContain('rm');
  });

  it('a dead link says it is gone, in both languages, and never says why', async () => {
    // AC-C7: unknown, expired and superseded are one answer. A page that distinguished them
    // would confirm to anybody guessing that a token exists.
    readSupplierRequest.mockRejectedValue(new Unavailable('gone'));
    await renderPage();

    await waitFor(() => expect(screen.getByText(/此链接已失效/)).toBeInTheDocument());
    expect(screen.getByText(/This link is no longer available/)).toBeInTheDocument();
    const text = (document.body.textContent ?? '').toLowerCase();
    expect(text).not.toContain('expired');
    expect(text).not.toContain('unknown');
  });
});
