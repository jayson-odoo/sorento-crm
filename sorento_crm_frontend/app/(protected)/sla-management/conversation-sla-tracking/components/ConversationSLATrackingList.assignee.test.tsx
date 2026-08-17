/**
 * The listing's "Assigned To" cell (feedback 2026-08-16, item 1).
 *
 * Resolve NULLs the assignee, so every resolved row used to read "-" in the one
 * column a reader scans to find out who handled it. Same rule as the detail
 * header: assignee while open, resolver once resolved.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import ConversationSLATrackingList from './ConversationSLATrackingList';

const useConversationSLATracking = vi.fn();
const useSyncAssigneeFromRespond = vi.fn();

vi.mock('../hooks/useConversationSLATracking', () => ({
  useConversationSLATracking: (...a: unknown[]) => useConversationSLATracking(...a),
  useSyncAssigneeFromRespond: (...a: unknown[]) => useSyncAssigneeFromRespond(...a),
}));

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: () => ({ data: [] }),
    useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  };
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
  usePathname: () => '/sla-management/conversation-sla-tracking',
}));

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

// Rows only mount once the column-preferences read answers (it renders
// skeletons until then, and nothing answers it under jsdom).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

function rowsResponse(rows: Array<Record<string, unknown>>) {
  return {
    data: { data: rows, pagination: { total: rows.length, page: 1, limit: 50 } },
    isLoading: false,
    isFetching: false,
  };
}

const baseRow = {
  id: 'tr-1',
  policy_id: 'pol-1',
  current_tier: 1,
  initiated_at: '2026-08-12T02:00:00',
  current_tier_started_at: '2026-08-12T02:00:00',
  due_at: '2026-08-12T03:00:00',
  is_responded: false,
  is_resolved: false,
  contact_phone: '+60 12-334 5566',
  contact_name: 'Aisyah Rahman',
  policy_name: 'Conversation SLA - Standard',
};

beforeEach(() => {
  useConversationSLATracking.mockReset();
  useSyncAssigneeFromRespond.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

describe('ConversationSLATrackingList assignee cell', () => {
  it('an open row shows its assignee', async () => {
    useConversationSLATracking.mockReturnValue(
      rowsResponse([{ ...baseRow, assigned_user_name: 'Ben Lim' }]),
    );
    render(<ConversationSLATrackingList />);

    await waitFor(() => expect(screen.getByTitle('Assigned to Ben Lim')).toBeInTheDocument());
  });

  it('a resolved row shows who resolved it instead of a dash', async () => {
    useConversationSLATracking.mockReturnValue(
      rowsResponse([
        {
          ...baseRow,
          id: 'tr-2',
          is_resolved: true,
          resolved_at: '2026-08-12T04:00:00',
          assigned_user_name: null,
          resolved_by_user_name: 'Charissa Tan',
        },
      ]),
    );
    render(<ConversationSLATrackingList />);

    const cell = await screen.findByTitle('Resolved by Charissa Tan');
    expect(cell).toHaveTextContent('Resolved by Charissa Tan');
  });
});
