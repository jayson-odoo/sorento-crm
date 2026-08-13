import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactAttachmentTypesSection from './ContactAttachmentTypesSection';

const apiFetch = vi.fn();

vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const CATALOG = {
  data: [
    { id: 'baseline-1', type_name: 'Direct Access', code: null, is_direct_access: true, granted: false },
    { id: 'container-1', type_name: 'Container Status', code: null, is_direct_access: false, granted: true },
    { id: 'photos-1', type_name: 'Product Photos', code: null, is_direct_access: false, granted: false },
  ],
  granted_ids: ['container-1'],
};

function ok(body: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation(() => ok(CATALOG));
  Element.prototype.scrollIntoView = vi.fn();
  (Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
});

afterEach(() => cleanup());

describe('ContactAttachmentTypesSection', () => {
  it('shows only the granted types as badges, not the baseline', async () => {
    // The baseline is not a grant we made. Listing it as one would suggest an
    // admin could revoke it here, which this screen cannot do.
    renderWithClient(<ContactAttachmentTypesSection contactId="c1" />);
    expect(await screen.findByText('Container Status')).toBeInTheDocument();
    expect(screen.queryByText('Direct Access')).not.toBeInTheDocument();
  });

  it('renders the empty state when nothing extra is granted', async () => {
    apiFetch.mockImplementation(() =>
      ok({ data: CATALOG.data.map((t) => ({ ...t, granted: false })), granted_ids: [] }),
    );
    renderWithClient(<ContactAttachmentTypesSection contactId="c1" />);
    expect(await screen.findByText(/dealer-facing documents only/i)).toBeInTheDocument();
  });

  it('locks the baseline tick on and disabled in the dialog', async () => {
    renderWithClient(<ContactAttachmentTypesSection contactId="c1" />);
    await screen.findByText('Container Status');
    fireEvent.click(screen.getByLabelText(/edit document types/i));

    const baseline = await screen.findByRole('checkbox', { name: /direct access/i });
    expect(baseline).toBeDisabled();
    expect(baseline).toHaveAttribute('data-state', 'checked');
  });

  it('adds a grant with no confirmation and sends the full set', async () => {
    renderWithClient(<ContactAttachmentTypesSection contactId="c1" />);
    await screen.findByText('Container Status');
    fireEvent.click(screen.getByLabelText(/edit document types/i));
    fireEvent.click(await screen.findByRole('checkbox', { name: /product photos/i }));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      const put = apiFetch.mock.calls.find((c) => (c[1] as { method?: string })?.method === 'PUT');
      expect(put).toBeTruthy();
      expect(JSON.parse((put![1] as { body: string }).body)).toEqual({
        attachment_type_ids: ['container-1', 'photos-1'],
      });
    });
  });

  it('confirms before revoking, because a revoke silently stops answers', async () => {
    renderWithClient(<ContactAttachmentTypesSection contactId="c1" />);
    await screen.findByText('Container Status');
    fireEvent.click(screen.getByLabelText(/edit document types/i));
    fireEvent.click(await screen.findByRole('checkbox', { name: /container status/i }));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(await screen.findByText(/this action cannot be undone/i)).toBeInTheDocument();
    expect(apiFetch.mock.calls.some((c) => (c[1] as { method?: string })?.method === 'PUT')).toBe(
      false,
    );

    fireEvent.click(screen.getByRole('button', { name: /^confirm$/i }));
    await waitFor(() => {
      const put = apiFetch.mock.calls.find((c) => (c[1] as { method?: string })?.method === 'PUT');
      expect(JSON.parse((put![1] as { body: string }).body)).toEqual({ attachment_type_ids: [] });
    });
  });
});
