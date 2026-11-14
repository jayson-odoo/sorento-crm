/**
 * RELATED-RECORDS-B (owner, 14 Nov): a sample request opened from the project's Samples Request
 * tab names that tab as its origin, so its page shows "Back to project" and returns here, not to
 * the Sample Requests list.
 */
import React from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { project, renderWithClient } from './relatedRecordsTestKit';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const push = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams('tab=sample-requests'),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('../../sample-requests/hooks/useSampleRequests', () => ({
  useProjectSampleRequestsQuery: () => ({
    data: {
      data: [
        {
          id: 'sr-1',
          request_no: 'SR-ZZT-0003',
          status: 'submitted',
          status_label: 'Submitted',
          stage: null,
          request_date: null,
          submitted_at: null,
          delivery_date: null,
          delivery_mode: null,
          customer_name: 'Zzt Builders',
          customer_code: null,
          project_id: 'p1',
          project_name: 'Zzt Harbour View',
          ship_to_name: null,
          salesperson_name: 'Amy Salesperson',
          line_count: 1,
          board_mounting: false,
        },
      ],
    },
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

import { SampleRequestsPanel } from './SampleRequestsPanel';

beforeEach(() => push.mockClear());

describe('Samples Request tab row click', () => {
  it('opens the sample request with Back to this project tab', () => {
    renderWithClient(<SampleRequestsPanel project={project()} />);
    fireEvent.click(screen.getByText('SR-ZZT-0003'));
    expect(push).toHaveBeenCalledWith(
      `/project-sales/sample-requests/sr-1?back=${encodeURIComponent('/project-sales/p1?tab=sample-requests')}`,
    );
  });
});
