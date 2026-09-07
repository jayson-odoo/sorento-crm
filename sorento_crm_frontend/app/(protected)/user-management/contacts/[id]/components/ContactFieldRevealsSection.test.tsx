/**
 * Chatbot growth r1, Slice C2 (AC-963, AC-965). Phase 2 test-first.
 *
 * Mocks `apiFetch` (the api-client boundary), the same pattern
 * `ContactMediaAccessSection.test.tsx` uses, so the hook -> service -> fetch
 * chain is exercised for real and only the network is stubbed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactFieldRevealsSection from './ContactFieldRevealsSection';

const apiFetch = vi.fn();

vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function ok(body: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

const KEYS = [
  { key: 'inventory.sellable', label: 'Sellable stock' },
  { key: 'purchase_orders.supplier', label: 'PO supplier' },
];

function mockApi(granted: string[] = [], putResponder?: (body: { granted: string[] }) => unknown) {
  apiFetch.mockImplementation((url: string, options?: { method?: string; body?: string }) => {
    if (url.includes('/field-reveal-keys')) {
      return ok({ items: KEYS });
    }
    if (options?.method === 'PUT') {
      const body = JSON.parse(options.body ?? '{}') as { granted: string[] };
      return ok(putResponder ? putResponder(body) : { granted: body.granted });
    }
    return ok({ granted });
  });
}

function renderWithClient(contactId = 'c1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactFieldRevealsSection contactId={contactId} />
    </QueryClientProvider>,
  );
}

function putCalls() {
  return apiFetch.mock.calls.filter(
    ([, options]: [string, { method?: string } | undefined]) => options?.method === 'PUT',
  );
}

beforeEach(() => {
  apiFetch.mockReset();
});

afterEach(() => cleanup());

describe('ContactFieldRevealsSection', () => {
  it('renders every key from the keys endpoint, off by default', async () => {
    mockApi([]);
    renderWithClient();

    expect(await screen.findByText('Sellable stock')).toBeInTheDocument();
    expect(screen.getByText('PO supplier')).toBeInTheDocument();
    expect(screen.getAllByText('Hidden')).toHaveLength(2);
  });

  it('ticking a key saves immediately with no confirmation', async () => {
    mockApi([]);
    renderWithClient();

    const toggle = await screen.findByRole('switch', { name: /reveal sellable stock/i });
    fireEvent.click(toggle);

    await waitFor(() => expect(putCalls()).toHaveLength(1));
    const [, options] = putCalls()[0];
    expect(JSON.parse((options as { body: string }).body)).toEqual({
      granted: ['inventory.sellable'],
    });
  });

  it('unticking a key opens a confirmation dialog before saving', async () => {
    mockApi(['inventory.sellable']);
    renderWithClient();

    const toggle = await screen.findByRole('switch', { name: /reveal sellable stock/i });
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));

    fireEvent.click(toggle);

    // No PUT yet: the dialog is up.
    expect(putCalls()).toHaveLength(0);
    expect(screen.getByText(/hide sellable stock\?/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Hide' }));

    await waitFor(() => expect(putCalls()).toHaveLength(1));
    const [, options] = putCalls()[0];
    expect(JSON.parse((options as { body: string }).body)).toEqual({ granted: [] });
  });

  it('cancelling the confirmation saves nothing', async () => {
    mockApi(['inventory.sellable']);
    renderWithClient();

    const toggle = await screen.findByRole('switch', { name: /reveal sellable stock/i });
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
    fireEvent.click(toggle);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(putCalls()).toHaveLength(0);
  });

  it('renders no fixed widths - stays usable at 375px', async () => {
    mockApi([]);
    const { container } = renderWithClient();
    await screen.findByText('Sellable stock');

    expect(container.querySelectorAll('[class*="w-["]').length).toBe(0);
    expect(container.querySelectorAll('[style*="width"]').length).toBe(0);
  });
});
