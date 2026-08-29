/**
 * S3-01 / S4-03 - the list reopens on the page it was left on.
 *
 * `useListStateFromUrl` restores page, sort, search and the status filter from
 * the URL Back handed back. A "reset to page 1 when the filter changes" effect
 * sitting beside it fires ON MOUNT as well, and stamps pageIndex 0 over the
 * value just restored, so Back from page 3 landed on page 1 and the whole round
 * trip was undone without a single error anywhere.
 *
 * The assertion is the params the list asks its question with, because that is
 * what the user sees: the page that gets fetched.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

let search = new URLSearchParams();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/marketing-management/campaigns',
  useSearchParams: () => search,
}));

const useCampaigns = vi.fn();
vi.mock('../hooks/useCampaigns', () => ({
  useCampaigns: (params: unknown) => useCampaigns(params),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import CampaignsList from './CampaignsList';

function lastParams() {
  return useCampaigns.mock.calls[useCampaigns.mock.calls.length - 1][0];
}

beforeEach(() => {
  vi.clearAllMocks();
  useCampaigns.mockReturnValue({
    data: { data: [], pagination: { total: 0 } },
    isLoading: false,
    refetch: vi.fn(),
    isFetching: false,
  });
});

describe('CampaignsList - the restored page survives its own filter effect', () => {
  it('S4-03: mounting on ?page=3&status=x keeps pageIndex 2', () => {
    search = new URLSearchParams('page=3&limit=25&status=active');
    render(<CampaignsList />);

    const params = lastParams();
    expect(params.pageIndex).toBe(2);
    expect(params.pageSize).toBe(25);
    expect(params.status).toBe('active');
  });

  it('S4-03: a list opened fresh from the sidebar keeps its own defaults', () => {
    search = new URLSearchParams();
    render(<CampaignsList />);

    expect(lastParams().pageIndex).toBe(0);
  });
});
