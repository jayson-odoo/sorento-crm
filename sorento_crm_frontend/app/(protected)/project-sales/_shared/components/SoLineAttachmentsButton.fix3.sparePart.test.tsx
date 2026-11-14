/**
 * SPARE-PART-ORDER-REQUEST fix round 3, B5 (browser pass): a failed photo upload on a request
 * line is never silent. The browser pass saw POST .../order-inquiry-rows/<row>/attachments answer
 * 400 with the dialog open and nothing on screen.
 *
 * What the existing SO-line upload does on failure (the control below): the hook's onError calls
 * `toast.error(<server message>)` and the dialog stays open with the picked file still listed.
 * Contract asserted for BOTH targets: the server's message reaches the user (a toast.error with
 * it, or the text inside the dialog), and the dialog stays open holding the file to retry.
 * Asserted at the HTTP seam (`apiFetch`) with the real hook and service.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: (...a: unknown[]) => toastError(...a), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: () => 'pending-action-1',
  dismissDeferredToast: vi.fn(),
}));

const MESSAGE = 'File storage is not configured. Ask an admin to set it up.';
const apiFetch = vi.fn(async (_url: string, init?: RequestInit) => {
  const method = (init?.method ?? 'GET').toUpperCase();
  if (method === 'POST' && /\/attachments$/.test(_url))
    return new Response(JSON.stringify({ message: MESSAGE, detail: null, code: null }), {
      status: 400,
      headers: { 'content-type': 'application/json' },
    });
  return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } });
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import { SoLineAttachmentsButton } from './SoLineAttachmentsButton';

const LABEL = 'Line 1 ZZX-100';

function mount(target: 'sales_order_line' | 'order_inquiry_row') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const props = {
    lineId: 'line-1',
    ...(target === 'order_inquiry_row' ? { target: { kind: 'order_inquiry_row', id: 'line-1' } } : {}),
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

async function failUpload() {
  fireEvent.click(screen.getByRole('button', { name: `Attachments for ${LABEL}` }));
  const zone = screen.getByRole('button', { name: /drop|browse|choose/i });
  fireEvent.drop(zone, {
    dataTransfer: { files: [new File(['x'], 'worn-seal.png', { type: 'image/png' })] },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Upload' }));
  await waitFor(() =>
    expect(apiFetch.mock.calls.some(([, init]) => (init?.method ?? '').toUpperCase() === 'POST')).toBe(true),
  );
}

function errorShown(): boolean {
  const toasted = toastError.mock.calls.some((c) => String(c[0]).includes(MESSAGE));
  const inDialog = (screen.queryByRole('dialog')?.textContent ?? '').includes(MESSAGE);
  return toasted || inDialog;
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('B5: a failed upload is never silent', () => {
  it('control: a sales-order line upload that fails shows the server message and keeps the dialog', async () => {
    mount('sales_order_line');
    await failUpload();
    await waitFor(() => expect(errorShown()).toBe(true));
    expect(screen.getByRole('dialog')).toHaveTextContent('worn-seal.png');
  });

  it('a request line (OI row) upload that fails shows the server message and keeps the dialog', async () => {
    mount('order_inquiry_row');
    await failUpload();
    expect(
      apiFetch.mock.calls.some(([url]) => String(url).includes('/order-inquiry-rows/line-1/attachments')),
    ).toBe(true);
    await waitFor(() => expect(errorShown()).toBe(true));
    expect(screen.getByRole('dialog')).toHaveTextContent('worn-seal.png');
  });
});
