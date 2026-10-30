/**
 * PORTAL-P4-REQUESTS R3b portal pin: with NO SubmissionClientProvider the portal's PriceTagRequestForm is unchanged.
 * Every call stays on `/api/v1/public/portal/...` (never `/api/v1/my-requests`), Delete Draft is the portal's own
 * confirm dialog and then the immediate DELETE (no pending action), and navigation stays in the portal tree.
 * Seam: the global `fetch` the portal client uses.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const nav = vi.hoisted(() => ({ push: vi.fn() }));
const pending = vi.hoisted(() => ({ createPendingAction: vi.fn(), cancelPendingAction: vi.fn(), getCurrentPendingAction: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn(), dismiss: vi.fn() } }));
vi.mock('@/services/pendingActionService', () => pending);
vi.mock('@/components/common/AttachmentPreviewModal', () => ({ __esModule: true, default: () => null }));

interface Call { url: string; method: string }
const calls: Call[] = [];
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const DRAFT = {
  id: 'req-1', contact_id: 'ct-1', doc_number: 'PT-202610-0001', status: 'new', portal_draft_at: '2026-10-01T01:00:00',
  debtor_code: 'ZZT-D1', debtor_name: 'ZZT Dealer', needed_by_date: '2030-01-15', notes: null, price_mode: 'list',
  print_by: 'self', created_at: '2026-10-01T01:00:00', line_count: 0, revision_no: 0, attachments: [], lines: [],
  is_editable: true, review_round: 1,
  revision: { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: null },
};

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
  vi.stubGlobal('fetch', vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    calls.push({ url, method });
    const path = url.split('?')[0];
    if (path.endsWith('/me')) return json({ contact_id: 'c1', space_id: 'sp1', name: 'Ann Sales', phone_number: '60123456789', expires_at: '2030-01-01T00:00:00Z' });
    if (path.includes('/lookups/debtors-for-agent')) return json([{ customer_code: 'ZZT-D1', customer_name: 'ZZT Dealer', debtor_code: null, debtor_name: null }]);
    if (path.endsWith('/neighbours')) return json({ prev_id: null, next_id: null, position: 1, total: 1 });
    if (path.endsWith('/revisions') || path.endsWith('/comments')) return json({ items: [] });
    if (path.endsWith('/review-comments')) return json([]);
    if (path.includes('/lookups/')) return json([]);
    if (method === 'DELETE') return new Response(null, { status: 204 });
    return json(DRAFT);
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

import { PriceTagRequestForm } from './PriceTagRequestForm';

describe('PriceTagRequestForm without a provider is the portal, unchanged', () => {
  it('loads and saves through /api/v1/public/portal only', async () => {
    render(<PriceTagRequestForm requestId="req-1" />);
    fireEvent.click(await screen.findByRole('button', { name: /Save Draft/ }));
    await waitFor(() => expect(calls.some((c) => c.method === 'PUT' && c.url.includes('/api/v1/public/portal/submissions/price_tag_request/req-1'))).toBe(true));
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c.url.includes('/api/v1/public/portal/'))).toBe(true);
    expect(calls.some((c) => c.url.includes('/my-requests'))).toBe(false);
    await waitFor(() => expect(nav.push.mock.calls.some((a) => String(a[0]).startsWith('/portal'))).toBe(true));
  });

  it('Delete Draft asks with its own confirm, then DELETEs immediately (no pending action)', async () => {
    render(<PriceTagRequestForm requestId="req-1" />);
    fireEvent.click(await screen.findByRole('button', { name: /Delete Draft/ }));
    expect(await screen.findByText('Delete this draft?')).toBeInTheDocument();
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.url.includes('/api/v1/public/portal/submissions/price_tag_request/req-1'))).toBe(true));
    expect(pending.createPendingAction).not.toHaveBeenCalled();
    await waitFor(() => expect(nav.push.mock.calls.some((a) => String(a[0]).startsWith('/portal'))).toBe(true));
  });
});
