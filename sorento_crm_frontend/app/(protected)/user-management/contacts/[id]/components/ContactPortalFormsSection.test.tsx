/**
 * Contact Details -> Portal forms (PLAN-contact-portal-form-override AC-5).
 *
 * Mocks `apiFetch` (the api-client boundary), the same pattern
 * `ContactMediaAccessSection.test.tsx` uses, so the hook -> service -> fetch
 * chain is exercised for real and only the network is stubbed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactPortalFormsSection from './ContactPortalFormsSection';
import type { ContactPortalFormRow } from '../services/contactPortalFormsService';

const apiFetch = vi.fn();

vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function ok(body: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function row(overrides: Partial<ContactPortalFormRow> = {}): ContactPortalFormRow {
  return {
    form_type: 'price_tag_request',
    inherited: false,
    override: null,
    effective: false,
    ...overrides,
  };
}

function mockApi(
  getBody: unknown,
  putResponder?: (body: Record<string, unknown>) => unknown,
) {
  apiFetch.mockImplementation((url: string, options?: { method?: string; body?: string }) => {
    if (options?.method === 'PUT') {
      const body = JSON.parse(options.body ?? '{}');
      return ok(putResponder ? putResponder(body) : { forms: [row(body.overrides[0])] });
    }
    return ok(getBody);
  });
}

function renderWithClient(contactId = 'c1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactPortalFormsSection contactId={contactId} />
    </QueryClientProvider>,
  );
}

function putCalls() {
  return apiFetch.mock.calls.filter(
    (c) => (c[1] as { method?: string } | undefined)?.method === 'PUT',
  );
}

const openMenu = () =>
  fireEvent.click(document.querySelector('[data-slot="searchable-select-trigger"]')!);

beforeEach(() => {
  apiFetch.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());

describe('ContactPortalFormsSection', () => {
  it('renders the price tag row with its effective state', async () => {
    mockApi({ forms: [row({ inherited: true, effective: true })] });
    renderWithClient();

    expect(await screen.findByText('Price Tag Request')).toBeInTheDocument();
    expect(screen.getByText('Visible')).toBeInTheDocument();
  });

  it('shows Hidden when nothing is inherited and no override exists', async () => {
    mockApi({ forms: [row()] });
    renderWithClient();

    expect(await screen.findByText('Price Tag Request')).toBeInTheDocument();
    expect(screen.getByText('Hidden')).toBeInTheDocument();
  });

  it('selecting Always show issues a PUT with is_enabled true', async () => {
    mockApi({ forms: [row()] });
    renderWithClient();
    await screen.findByText('Price Tag Request');

    openMenu();
    fireEvent.click(await screen.findByText('Always show'));

    await waitFor(() => expect(putCalls()).toHaveLength(1));
    expect(JSON.parse(putCalls()[0][1].body)).toEqual({
      overrides: [{ form_type: 'price_tag_request', is_enabled: true }],
    });
  });

  it('selecting Inherit issues a PUT with is_enabled null', async () => {
    mockApi({ forms: [row({ override: true, effective: true })] });
    renderWithClient();
    await screen.findByText('Price Tag Request');

    openMenu();
    fireEvent.click(await screen.findByText('Inherit from access types'));

    await waitFor(() => expect(putCalls()).toHaveLength(1));
    expect(JSON.parse(putCalls()[0][1].body)).toEqual({
      overrides: [{ form_type: 'price_tag_request', is_enabled: null }],
    });
  });

  it('never renders a UUID', async () => {
    mockApi({ forms: [row()] });
    const { container } = renderWithClient('11111111-2222-3333-4444-555555555555');
    await screen.findByText('Price Tag Request');

    expect(container.textContent).not.toMatch(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
    );
  });
});
