/**
 * F8 - what the supplier sees when they open the link (AC-C6, AC-C7).
 *
 * Two properties worth a test, and they are both about what is NOT on the page: a stranger
 * holding the URL must not read a price, and a dead link must not say WHY it is dead. The
 * rest is that the bilingual labels are actually bilingual - the reader acting on this page
 * reads Chinese, and an English-only header is a page they cannot use.
 *
 * The service is mocked at the module boundary; nothing hits the network.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';

import PublicSupplierRequestPage from './page';
import type { SupplierRequest } from '../../../lib/publicSupplierRequestService';

const readSupplierRequest = vi.fn();
const readSupplierRequestDocument = vi.fn();

class Unavailable extends Error {}

vi.mock('../../../lib/publicSupplierRequestService', () => ({
  readSupplierRequest: (...args: unknown[]) => readSupplierRequest(...args),
  readSupplierRequestDocument: (...args: unknown[]) => readSupplierRequestDocument(...args),
  SupplierRequestUnavailableError: class extends Error {},
}));

const REQUEST: SupplierRequest = {
  supplier_name: 'CHAOZHOU JINBAICHUAN SANITARY WARE TECHNOLOGY CO., LTD',
  requested_at: '2026-07-31T02:00:00',
  line_count: 2,
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
  });

  it('writes every label in Chinese and English', async () => {
    await renderPage();

    await waitFor(() => expect(screen.getByText(/配柜要求/)).toBeInTheDocument());
    expect(screen.getByText(/型号 \/ Item/)).toBeInTheDocument();
    expect(screen.getByText(/需装数量 \/ Qty to load/)).toBeInTheDocument();
    expect(screen.getByText(/包装好库存 \/ Packed/)).toBeInTheDocument();
    expect(screen.getByText(/空瓷 \/ Unfinished/)).toBeInTheDocument();
  });

  it('shows their own figures, and a dash where they have never listed the item', async () => {
    await renderPage();

    await waitFor(() => expect(screen.getByText('120')).toBeInTheDocument());
    expect(screen.getByText('340')).toBeInTheDocument();
    expect(screen.getAllByText('-').length).toBeGreaterThanOrEqual(2);
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
