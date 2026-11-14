/**
 * SPARE-PART-OR-B C, red-first (Phase 2). C3.3 / C3.4: the OI page History of a spare part
 * inquiry reads `view=inquiry` (from the first raise on); the OR page keeps the whole life.
 * Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md.
 *
 * NAMED CONTRACT CHOICES (the UAC leaves them open):
 * 1. `getOrderInquiryHistory(id, { view: 'inquiry' })` calls
 *    `GET .../order-inquiry-headers/{id}/history?view=inquiry`; with no options the URL has no
 *    query (the OR page).
 * 2. `OrderInquiryHistory` and `OrderInquiryLineHistoryDialog` take `view?: 'inquiry'` and pass
 *    it on. `OrderInquiryDetail` passes `view="inquiry"` to both for a spare part inquiry;
 *    `SparePartRequestRecord` passes none. Those two wirings are checked on the source (the
 *    detail page needs a dozen mocks to mount; the props are what this test pins).
 */
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn(
  async (_url: string) =>
    new Response(JSON.stringify({ events: [] }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
);
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string]) => apiFetch(...a) }));

import { getOrderInquiryHistory } from '../../../_shared/services/orderInquiryService';
import { OrderInquiryHistory } from './OrderInquiryHistory';

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

function urls(): string[] {
  return apiFetch.mock.calls.map((c) => String(c[0]));
}

function mount(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe('C3.4: the history service', () => {
  it('asks for view=inquiry when told to', async () => {
    await (getOrderInquiryHistory as unknown as (id: string, o: unknown) => Promise<unknown>)(
      'oi-1',
      { view: 'inquiry' },
    );
    expect(urls().some((u) => /\/order-inquiry-headers\/oi-1\/history\?view=inquiry$/.test(u))).toBe(true);
  });

  it('asks for the whole life with no options', async () => {
    await getOrderInquiryHistory('oi-1');
    expect(urls().some((u) => /\/order-inquiry-headers\/oi-1\/history$/.test(u))).toBe(true);
  });
});

describe('C3.3: the History tab component', () => {
  it('view="inquiry" reads the inquiry history', async () => {
    const Comp = OrderInquiryHistory as unknown as React.ComponentType<Record<string, unknown>>;
    mount(<Comp inquiryId="oi-1" view="inquiry" />);
    await waitFor(() =>
      expect(urls().some((u) => u.endsWith('/order-inquiry-headers/oi-1/history?view=inquiry'))).toBe(true),
    );
  });

  it('no view reads the whole life', async () => {
    mount(<OrderInquiryHistory inquiryId="oi-1" />);
    await waitFor(() => expect(urls().some((u) => u.endsWith('/order-inquiry-headers/oi-1/history'))).toBe(true));
    expect(urls().some((u) => u.includes('view=inquiry'))).toBe(false);
  });
});

const HERE = path.dirname(new URL(import.meta.url).pathname);
const read = (rel: string) => fs.readFileSync(path.resolve(HERE, rel), 'utf8');
/** Every `<Tag ... />` element of `source`, as text (props may hold arrow functions). */
function elements(source: string, tag: string): string[] {
  const out: string[] = [];
  let at = source.indexOf(`<${tag}`);
  while (at >= 0) {
    out.push(source.slice(at, source.indexOf('/>', at)));
    at = source.indexOf(`<${tag}`, at + 1);
  }
  return out;
}

describe('C3.3: who asks for which view', () => {
  it('the OI page passes view="inquiry" to its History tab and line popup', () => {
    const source = read('./OrderInquiryDetail.tsx');
    expect(elements(source, 'OrderInquiryHistory ').some((e) => /\bview=/.test(e))).toBe(true);
    expect(elements(source, 'OrderInquiryLineHistoryDialog').some((e) => /\bview=/.test(e))).toBe(true);
  });

  it('the line popup forwards view to the history it shows', () => {
    const source = read('./OrderInquiryLineHistoryDialog.tsx');
    expect(elements(source, 'OrderInquiryHistory ').some((e) => /\bview=\{view\}/.test(e))).toBe(true);
  });

  it('the OR page keeps the whole life (no view)', () => {
    const source = read(
      '../../../../procurement-management/spare-part-requests/components/SparePartRequestRecord.tsx',
    );
    const history = elements(source, 'OrderInquiryHistory ');
    expect(history.length).toBeGreaterThan(0);
    expect(history.some((e) => /\bview=/.test(e))).toBe(false);
  });
});
