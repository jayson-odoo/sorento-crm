import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { apiFetch } from '@/lib/api';
import ContactCsRoutingTable from './ContactCsRoutingTable';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

function route(candidates: unknown[], pins: unknown[]) {
  mockApiFetch.mockImplementation((url: string) => {
    if (url.endsWith('/cs-routing/candidates')) {
      return Promise.resolve(jsonResponse({ candidates }));
    }
    if (url.endsWith('/cs-routing')) {
      return Promise.resolve(jsonResponse({ pins }));
    }
    return Promise.resolve(jsonResponse({}));
  });
}

function renderTable() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ContactCsRoutingTable contactId="c1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockApiFetch.mockReset();
});

describe('ContactCsRoutingTable', () => {
  it('shows an empty state when no CS team is configured', async () => {
    route([], []);
    renderTable();
    await waitFor(() =>
      expect(
        screen.getByText(/No customer-service team configured yet/i),
      ).toBeInTheDocument(),
    );
  });

  it('renders a row per procurement use_case when a CS team exists', async () => {
    route(
      [
        { id: 'u1', name: 'Aishah', email: 'aishah@x.com' },
        { id: 'u2', name: 'Maryam', email: 'maryam@x.com' },
      ],
      [{ use_case: 'purchase_request', cs_pic_user_id: 'u1', cs_pic_name: 'Aishah' }],
    );
    renderTable();
    await waitFor(() =>
      expect(screen.getByText('Purchase Request')).toBeInTheDocument(),
    );
    expect(screen.getByText('Sponsorship Form')).toBeInTheDocument();
    // Helper copy explaining the pin behaviour renders.
    expect(
      screen.getByText(/Pin this salesman to a specific customer-service PIC/i),
    ).toBeInTheDocument();
  });
});
