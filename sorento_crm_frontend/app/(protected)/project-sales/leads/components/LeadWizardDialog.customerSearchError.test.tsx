/**
 * LEAD-GOVERNS-REGISTER LGR-A5: a failed customer search shows the picker's own error state with
 * Retry, never an empty list. Uses the REAL SearchableSelect (its async mode owns that state).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
if (!('ResizeObserver' in window)) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

const listCustomerOptions = vi.fn();

vi.mock('../../_shared/services/projectService', () => ({
  createLead: vi.fn(),
  listCustomerOptions: (...args: unknown[]) => listCustomerOptions(...args),
  listParties: vi.fn(async () => ({ data: [], pagination: { total: 0, page: 1, limit: 200 } })),
  listLeads: vi.fn(),
  getLead: vi.fn(),
  updateLead: vi.fn(),
  listProjects: vi.fn(),
}));
vi.mock('../../_shared/services/leadAcceptanceService', () => ({
  listAwaitingAcceptance: vi.fn(),
  assignLead: vi.fn(),
  acceptLead: vi.fn(),
  declineLead: vi.fn(),
  nudgeLeadAssignee: vi.fn(),
}));
vi.mock('@/services/userSelectService', () => ({ getUserLookup: vi.fn(async () => []) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-me', name: 'Sales A' } }, status: 'authenticated' }),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));

import { LeadWizardDialog } from './LeadWizardDialog';

beforeEach(() => vi.clearAllMocks());

describe('LeadWizardDialog customer search failure (LGR-A5)', () => {
  it('shows a Retry that searches again, not an empty list', async () => {
    listCustomerOptions.mockRejectedValueOnce(new Error('Server error. Try again or contact support.'));
    listCustomerOptions.mockResolvedValue([{ value: 'c1', label: 'KEDAI CONTOH SDN. BHD.' }]);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <LeadWizardDialog onDone={vi.fn()} />
      </QueryClientProvider>,
    );
    fireEvent.click(document.querySelector('[data-slot="searchable-select-trigger"]') as HTMLElement);
    const retry = await screen.findByRole('button', { name: /retry/i });
    expect(screen.queryByText('No results found.')).not.toBeInTheDocument();
    fireEvent.click(retry);
    await waitFor(() => expect(listCustomerOptions).toHaveBeenCalledTimes(2));
  });
});
