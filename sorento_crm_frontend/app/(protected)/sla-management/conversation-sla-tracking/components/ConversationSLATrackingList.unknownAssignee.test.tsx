/**
 * FILTER-MULTISELECT PR2 review: an assignee id the options do not hold (an old link, or before the user
 * lookup answers) is never shown as its own label: no UUID appears in the Assignee trigger. Uses the real
 * SearchableMultiSelect. Harness mirrors ConversationSLATrackingList.multiAssignee.test.tsx.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ConversationSLATrackingList from './ConversationSLATrackingList';

const useConversationSLATracking = vi.fn();

vi.mock('../hooks/useConversationSLATracking', () => ({
  useConversationSLATracking: (...a: unknown[]) => useConversationSLATracking(...a),
  useSyncAssigneeFromRespond: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteConversationSLATracking: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-ann', respond_user_id: 'resp-ann', name: 'Ann Lee', email: 'ann@e.com' },
    { id: 'u-ben', respond_user_id: 'resp-ben', name: 'Ben Lim', email: 'ben@e.com' },
    { id: 'u-cat', respond_user_id: null, name: 'Cat Tan', email: 'cat@e.com' },
  ]),
}));
const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(url.search),
  usePathname: () => '/sla-management/conversation-sla-tracking',
}));
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const row = {
  id: 'tr-1', policy_id: 'pol-1', current_tier: 1, initiated_at: '2026-08-12T02:00:00',
  current_tier_started_at: '2026-08-12T02:00:00', due_at: '2026-08-12T03:00:00', is_responded: false,
  is_resolved: false, contact_phone: '+60 12-000 0553', contact_name: 'Aisyah Rahman',
  policy_name: 'Conversation SLA - Standard', assigned_user_name: 'Ben Lim',
};


const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-/i;
const ORPHAN = '9f1b6c52-4d1e-4a39-8a77-0c2d5e8b1f34';

beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  useConversationSLATracking.mockReset();
  useConversationSLATracking.mockReturnValue({
    data: { data: [row], pagination: { total: 1, page: 1, limit: 50 } },
    isLoading: false,
    isFetching: false,
  });
});
afterEach(() => cleanup());

describe('Conversation SLA list - an assignee id the options do not hold', () => {
  it('shows no UUID in the Assignee trigger', async () => {
    url.search = `assigned_to=${ORPHAN}`;
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ConversationSLATrackingList />
      </QueryClientProvider>,
    );
    await screen.findByText('Aisyah Rahman');
    await user.click(await screen.findByRole('button', { name: /^filters/i }));
    await screen.findAllByText('Filters');
    expect(document.body.textContent ?? '').not.toMatch(UUID);
  });
});
