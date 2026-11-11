/**
 * PROJECT-STAGE-ACTIONS (crew pass 11 Nov): the project's Sponsorships tab shows what each form
 * SPONSORS (its Grand total), not the project's value the form also carries.
 */
import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('../../_shared/hooks/useProjects', () => ({
  useProjectSponsorships: () => ({
    data: [
      {
        id: 'sf-1',
        request_number: 'SF2611001',
        status: 'submitted',
        total_project_value: '100000.00',
        sponsored_total: '20.00',
      },
    ],
    isLoading: false,
    isError: false,
  }),
  useSponsorshipRollup: () => ({
    data: { project_id: 'p1', total: '20.00', form_count: 1, by_year: [] },
  }),
}));

import { SponsorshipsPanel } from './SponsorshipsPanel';

describe('Sponsorships tab value', () => {
  it('shows the sponsored total, never the project value', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SponsorshipsPanel project={{ id: 'p1' } as never} />
      </QueryClientProvider>,
    );
    expect(screen.getAllByText(/RM\s?20\.00/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/100,000/)).toBeNull();
  });

  it('opens a form so that its Back returns to this tab', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SponsorshipsPanel project={{ id: 'p1' } as never} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByText('SF2611001'));
    expect(push).toHaveBeenCalledWith(
      `/procurement-management/sponsorship-forms/sf-1?back=${encodeURIComponent('/project-sales/p1?tab=sponsorships')}`,
    );
  });
});
