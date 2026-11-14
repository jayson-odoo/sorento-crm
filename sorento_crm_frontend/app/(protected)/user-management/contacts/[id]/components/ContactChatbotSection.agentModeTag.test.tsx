/**
 * AGENT-MODE-TAG: the Agent mode (auto) switch names the tag its value comes from. Red first.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactChatbotSection from './ContactChatbotSection';

const useContactChatbotProfile = vi.fn();
const mutate = vi.fn();

const getContactTagSettings = vi.fn();
vi.mock('../services/contactTagSettingsService', () => ({
  getContactTagSettings: (...a: unknown[]) => getContactTagSettings(...a),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('../hooks/useContactChatbot', () => ({
  useContactChatbotProfile: (...a: unknown[]) => useContactChatbotProfile(...a),
  useSaveContactChatbotProfile: () => ({ mutate, isPending: false }),
  useSaveContactEscalation: () => ({ mutate: vi.fn(), isPending: false }),
  useSaveContactChatbotAllowed: () => ({ mutate: vi.fn(), isPending: false }),
  useContactChatbotMemory: () => ({
    data: {
      level: { own: null, effective: 'off', system_default: 'off' },
      facts: [],
      vocabulary: [],
      episodes: { kept: 0, limit: 20, current: null, rows: [] },
      open_orders: { customer_name: null, rows: [] },
    },
    isLoading: false,
    isError: false,
  }),
  useSaveContactFact: () => ({ mutate: vi.fn(), isPending: false }),
  contactChatbotMemoryQueryKey: (contactId: string) => ['contact-chatbot-memory', contactId],
}));

const BASE_PROFILE = {
  chatbot_memory_level: null,
  tier: null,
  default_ledgers: [],
  stock_allowed: true,
  notify_salesman: false,
  packing_list_allowed: false,
  eta_offset_applied: true,
  escalation_allowed: true,
  chatbot_allowed: true,
  skip_period_questions: false,
  files_as_links: false,
  agent_enabled: true,
  chatbot_agent_daily_turns: null as number | null,
};

function mount(profile = BASE_PROFILE) {
  useContactChatbotProfile.mockReturnValue({ data: profile, isLoading: false, isError: false });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactChatbotSection contactId="c1" />
    </QueryClientProvider>,
  );
}

const item = (over: Record<string, unknown>) => ({
  section: 'chatbot',
  key: 'chatbot_agent_enabled',
  label: 'Agent mode',
  current: true,
  expected: true,
  decided_by: ['Dealer tag'],
  conflict: false,
  conflict_tags: [],
  differs: false,
  ...over,
});

beforeEach(() => {
  useContactChatbotProfile.mockReset();
  getContactTagSettings.mockReset();
});
afterEach(() => cleanup());

describe('ContactChatbotSection - agent mode from a tag (AGENT-MODE-TAG)', () => {
  it('names the tag that sets agent mode', async () => {
    getContactTagSettings.mockResolvedValue({ status: 'matches', tags: [], items: [item({})] });
    mount();
    expect(await screen.findByText('From tag Dealer tag')).toBeInTheDocument();
  });

  it('says nothing when this contact was changed away from what the tag says', async () => {
    getContactTagSettings.mockResolvedValue({
      status: 'differs',
      tags: [],
      items: [item({ current: false, differs: true })],
    });
    mount();
    await waitFor(() => expect(getContactTagSettings).toHaveBeenCalled());
    expect(screen.queryByText(/From tag/)).not.toBeInTheDocument();
  });

  it('says nothing when no tag sets agent mode', async () => {
    getContactTagSettings.mockResolvedValue({
      status: 'matches',
      tags: [],
      items: [item({ key: 'chatbot_allowed', label: 'AI replies' })],
    });
    mount();
    await waitFor(() => expect(getContactTagSettings).toHaveBeenCalled());
    expect(screen.queryByText(/From tag/)).not.toBeInTheDocument();
  });
});
