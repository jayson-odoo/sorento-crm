/**
 * SPARE-PART-ORDER-REQUEST review round 2 (browser pass 5, step 8), red-first (Phase 2).
 *
 * R9 owner standing rule "one value per field, no ' · ' joins": the shared OrderInquiryHistory
 *    (the spare part record page's History tab and the OI page's) renders each entry's
 *    date-time and its person in their OWN elements, and no " · " appears anywhere in a History
 *    row (today AuditTrail joins them: "13/11/2026, 2:07 pm · by Approver B", and a
 *    many-line entry adds "· Show 2 lines").
 *
 * Existing coverage not duplicated: OrderInquiryDetail.test.tsx (STANDARD-HISTORY) checks the
 * tab and the fetch only; components/audit/AuditTrail.actor.test.tsx checks the "by <actor>"
 * words by regex, which the fix keeps.
 *
 * Asserted at the HTTP seam (`apiFetch`): GET /order-inquiry-headers/<id>/history.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/procurement-management/spare-part-requests/spr-1',
  useSearchParams: () => new URLSearchParams(''),
}));

const EVENTS = [
  {
    id: 'ev-1',
    kind: 'approved',
    at: '2026-11-13T06:07:00',
    actor: 'Approver B',
    title: 'Approved',
    lines: [
      { row_id: 'row-1', so_line_no: null, item_code: 'SP-SEAL-40', qty: 2, change: 'Qty 2' },
    ],
  },
  {
    id: 'ev-2',
    kind: 'edited',
    at: '2026-11-13T05:00:00',
    actor: 'ZZT Alice',
    title: 'Edited, approval restarted',
    lines: [
      { row_id: 'row-1', so_line_no: null, item_code: 'SP-SEAL-40', qty: 2, change: 'Qty 1 to 2' },
      { row_id: 'row-2', so_line_no: null, item_code: 'SP-HINGE', qty: 4, change: 'Qty 3 to 4' },
    ],
  },
];

const apiFetch = vi.fn(async (url: string) => {
  const body = url.includes('/history') ? { events: EVENTS } : {};
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
});
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: (...a: [string, RequestInit?]) => apiFetch(a[0]),
}));

import { OrderInquiryHistory } from './OrderInquiryHistory';

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderInquiryHistory inquiryId="spr-1" />
    </QueryClientProvider>,
  );
}

const entries = () => Array.from(document.querySelectorAll<HTMLElement>('[data-audit-entry]'));

/** Elements whose OWN full text is exactly `pattern` (one value, one element). */
const ownText = (root: HTMLElement, pattern: RegExp) =>
  Array.from(root.querySelectorAll<HTMLElement>('*')).filter((el) =>
    pattern.test((el.textContent ?? '').trim()),
  );

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('R9: History rows carry one value per element, no " · " joins', () => {
  it('no History row contains a " · " join', async () => {
    mount();
    await screen.findByText('Approved');
    expect(entries().length).toBe(2);
    const joined = entries()
      .map((el) => (el.textContent ?? '').trim())
      .filter((text) => text.includes('·'));
    expect(joined, `rows with a " · " join: ${joined.join(' | ')}`).toEqual([]);
  });

  it('the person is in an element of its own', async () => {
    mount();
    await screen.findByText('Approved');
    const [approved] = entries();
    expect(
      ownText(approved, /^(by )?Approver B$/).length,
      `an element holding only the person, in: ${approved.textContent}`,
    ).toBeGreaterThan(0);
  });

  it('the date-time is in an element of its own (guard)', async () => {
    mount();
    await screen.findByText('Approved');
    const [approved] = entries();
    expect(
      ownText(approved, /^\d{2}\/\d{2}\/\d{4}, \d{1,2}:\d{2}( (am|pm))?$/i).length,
      `an element holding only the date-time, in: ${approved.textContent}`,
    ).toBeGreaterThan(0);
  });
});

describe('R15: History row text reads cleanly for copy and screen readers', () => {
  it('whitespace separates the date-time from "by <person>", still with no " · "', async () => {
    mount();
    await screen.findByText('Approved');
    const [approved] = entries();
    const text = approved.textContent ?? '';
    expect(text, `row text: ${text}`).toMatch(/\d{1,2}:\d{2}( (am|pm))?\s+by Approver B/i);
    expect(text).not.toContain('·');
  });
});
