/**
 * SPARE-PART-ORDER-REQUEST F4 (UAC R4, A3): the paperclip + lightbox takes its TARGET (a
 * sales-order line or an order-inquiry row) instead of a hard-wired SO-line service. Given an
 * OI-row target, an upload goes to `POST /api/v1/project-sales/order-inquiry-rows/{row_id}/
 * attachments` and never to the sales-order-line route.
 *
 * Asserted at the HTTP seam (`apiFetch`), so it holds however the coder splits the service
 * and hook. NAMED ASSUMPTION: the prop is `target={{ kind: 'order_inquiry_row', id }}`
 * (`lineId` is passed too, so an SO-line-only component still renders and the red is the
 * wrong URL, not a crash). Harness copied from `SoLineAttachmentsButton.test.tsx`.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver =
  IntersectionObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const calls: Array<{ url: string; method: string }> = [];
const apiFetch = vi.fn(async (url: string, init?: RequestInit) => {
  calls.push({ url, method: (init?.method ?? 'GET').toUpperCase() });
  return new Response('[]', { status: 200, headers: { 'content-type': 'application/json' } });
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: () => 'pending-action-1',
  dismissDeferredToast: vi.fn(),
}));

import { SoLineAttachmentsButton } from './SoLineAttachmentsButton';

const LABEL = 'OI-2611-0007 SP-SEAL-40';

function renderOiRow() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const props = {
    lineId: 'oi-row-1',
    target: { kind: 'order_inquiry_row', id: 'oi-row-1' },
    label: LABEL,
    attachments: [],
    canEdit: true,
  } as unknown as React.ComponentProps<typeof SoLineAttachmentsButton>;
  return render(
    <QueryClientProvider client={qc}>
      <SoLineAttachmentsButton {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  calls.length = 0;
  vi.clearAllMocks();
});

describe('F4 / UAC R4: an OI-row target uploads to the OI-row route', () => {
  it('posts the files to /order-inquiry-rows/{id}/attachments, never the SO-line route', async () => {
    renderOiRow();
    fireEvent.click(screen.getByRole('button', { name: `Attachments for ${LABEL}` }));
    const zone = screen.getByRole('button', { name: /drop|browse|choose/i });
    fireEvent.drop(zone, {
      dataTransfer: { files: [new File(['x'], 'worn-seal.png', { type: 'image/png' })] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true));
    const posts = calls.filter((c) => c.method === 'POST');
    expect(posts.map((c) => c.url)).toContain(
      '/api/v1/project-sales/order-inquiry-rows/oi-row-1/attachments',
    );
    expect(calls.some((c) => c.url.includes('/sales-order-lines/'))).toBe(false);
  });
});
