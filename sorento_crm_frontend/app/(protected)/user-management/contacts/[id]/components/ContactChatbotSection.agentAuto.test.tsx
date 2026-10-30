/**
 * AGENTIC-P2-ROUTE K3: the Agent switch reads "Agent mode (auto)" and a per-day cap input
 * sits next to it (blank = use the global value, clearable). Red first.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactChatbotSection from './ContactChatbotSection';

const useContactChatbotProfile = vi.fn();
const mutate = vi.fn();

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

const cap = () => screen.getByLabelText('Agent turns per day') as HTMLInputElement;

beforeEach(() => {
  useContactChatbotProfile.mockReset();
  mutate.mockReset();
});
afterEach(() => cleanup());

describe('ContactChatbotSection - Agent mode (auto) and the daily cap (K3)', () => {
  it('the switch is labelled "Agent mode (auto)"', () => {
    mount();
    expect(screen.getByLabelText('Agent mode (auto)')).toHaveAttribute('data-state', 'checked');
    expect(screen.queryByLabelText('Agent mode')).not.toBeInTheDocument();
  });

  it('a null cap renders a blank input', () => {
    mount();
    expect(cap().value).toBe('');
  });

  it('a set cap renders its value', () => {
    mount({ ...BASE_PROFILE, chatbot_agent_daily_turns: 7 });
    expect(cap().value).toBe('7');
  });

  it('typing a number saves it through the profile mutation', () => {
    mount();
    fireEvent.change(cap(), { target: { value: '9' } });
    fireEvent.blur(cap());
    expect(mutate).toHaveBeenCalled();
    expect(mutate.mock.calls.at(-1)![0]).toEqual({ ...BASE_PROFILE, chatbot_agent_daily_turns: 9 });
  });

  it('the clear button empties it to null', () => {
    const loaded = { ...BASE_PROFILE, chatbot_agent_daily_turns: 7 };
    mount(loaded);
    fireEvent.click(screen.getByRole('button', { name: /clear agent turns per day/i }));
    expect(mutate.mock.calls.at(-1)![0]).toEqual({ ...loaded, chatbot_agent_daily_turns: null });
  });

  it('a blank cap offers no clear button', () => {
    mount();
    expect(screen.queryByRole('button', { name: /clear agent turns per day/i })).not.toBeInTheDocument();
  });

  it('flipping the switch keeps the cap in the saved profile', () => {
    const loaded = { ...BASE_PROFILE, chatbot_agent_daily_turns: 7 };
    mount(loaded);
    fireEvent.click(screen.getByLabelText('Agent mode (auto)'));
    expect(mutate.mock.calls[0][0]).toEqual({ ...loaded, agent_enabled: false });
  });
});
