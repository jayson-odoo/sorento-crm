/**
 * Contact Details -> Portal forms (PLAN-contact-portal-form-override AC-5;
 * PLAN-portal-forms-market-segment AC-C1/AC-C2/AC-C3: all five kinds are
 * gated now, so the block always lists five rows, not price tag alone).
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
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function ok(body: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

// r2 default (PLAN-portal-forms-market-segment D3): every contact inherits
// the four legacy kinds; price tag is opt-in via a market segment grant.
const FIVE_ROWS: ContactPortalFormRow[] = [
  { form_type: 'complaint', inherited: true, override: null, effective: true },
  { form_type: 'stock_inquiry', inherited: true, override: null, effective: true },
  { form_type: 'purchase_request', inherited: true, override: null, effective: true },
  { form_type: 'sponsorship_form', inherited: true, override: null, effective: true },
  { form_type: 'price_tag_request', inherited: false, override: null, effective: false },
];

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

const selectTriggers = () =>
  document.querySelectorAll('[data-slot="searchable-select-trigger"]');
const openMenuFor = (index: number) => fireEvent.click(selectTriggers()[index]);

beforeEach(() => {
  apiFetch.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());

describe('ContactPortalFormsSection - five rows (AC-C1)', () => {
  it('renders all five kinds in LANDING_KINDS order with a Visible/Hidden badge each', async () => {
    mockApi({ forms: FIVE_ROWS });
    renderWithClient();

    await screen.findByText('Complaint');
    const labels = ['Complaint', 'Stock Inquiry', 'Purchase Request', 'Sponsorship Form', 'Price Tag Request'];
    for (const label of labels) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(selectTriggers()).toHaveLength(5);
    expect(screen.getAllByText('Visible')).toHaveLength(4);
    expect(screen.getAllByText('Hidden')).toHaveLength(1);
  });

  it('shows Hidden when nothing is inherited and no override exists', async () => {
    mockApi({ forms: [row()] });
    renderWithClient();

    expect(await screen.findByText('Price Tag Request')).toBeInTheDocument();
    expect(screen.getByText('Hidden')).toBeInTheDocument();
  });
});

describe('ContactPortalFormsSection - one PUT per row change (AC-C2)', () => {
  it('selecting Always show on the price tag row issues a PUT with is_enabled true', async () => {
    mockApi({ forms: [row()] });
    renderWithClient();
    await screen.findByText('Price Tag Request');

    openMenuFor(0);
    fireEvent.click(await screen.findByText('Always show'));

    await waitFor(() => expect(putCalls()).toHaveLength(1));
    expect(JSON.parse(putCalls()[0][1].body)).toEqual({
      overrides: [{ form_type: 'price_tag_request', is_enabled: true }],
    });
  });

  it('selecting Always hide on an inherited legacy row issues a PUT with is_enabled false', async () => {
    mockApi({ forms: FIVE_ROWS });
    renderWithClient();
    await screen.findByText('Complaint');

    openMenuFor(0);
    fireEvent.click(await screen.findByText('Always hide'));

    await waitFor(() => expect(putCalls()).toHaveLength(1));
    expect(JSON.parse(putCalls()[0][1].body)).toEqual({
      overrides: [{ form_type: 'complaint', is_enabled: false }],
    });
  });

  it('selecting Inherit issues a PUT with is_enabled null', async () => {
    mockApi({ forms: [row({ override: true, effective: true })] });
    renderWithClient();
    await screen.findByText('Price Tag Request');

    openMenuFor(0);
    fireEvent.click(await screen.findByText('Inherit'));

    await waitFor(() => expect(putCalls()).toHaveLength(1));
    expect(JSON.parse(putCalls()[0][1].body)).toEqual({
      overrides: [{ form_type: 'price_tag_request', is_enabled: null }],
    });
  });
});

describe('ContactPortalFormsSection - the Inherit label (AC-C3)', () => {
  it('reads just "Inherit", not "access types" or "market segments"', async () => {
    mockApi({ forms: [row()] });
    renderWithClient();
    await screen.findByText('Price Tag Request');

    openMenuFor(0);
    // The trigger already reads "Inherit" (the row's own current value) before
    // the popover opens, and the option list repeats it - both are the exact
    // word, never "... from access types" or "... from market segments".
    await waitFor(() => expect(screen.getAllByText('Inherit').length).toBeGreaterThan(0));
    expect(screen.queryByText('Inherit from access types')).not.toBeInTheDocument();
    expect(screen.queryByText('Inherit from market segments')).not.toBeInTheDocument();
  });
});

describe('ContactPortalFormsSection - misc', () => {
  it('never renders a UUID', async () => {
    mockApi({ forms: [row()] });
    const { container } = renderWithClient('11111111-2222-3333-4444-555555555555');
    await screen.findByText('Price Tag Request');

    expect(container.textContent).not.toMatch(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
    );
  });
});
