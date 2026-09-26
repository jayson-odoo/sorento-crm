/**
 * S6 (coordinator ruling, 16 Sep 2026): stock allowance moves onto the CRM contact,
 * default ON. `ContactChatbotSection` gains a "Stock checks" Switch bound to
 * `profile.stock_allowed`, checked by default; a change sends `stock_allowed` through
 * `save.mutate`. RIGHT NOW every test here is RED - the component renders no such
 * Switch and `ContactChatbotProfile` carries no `stock_allowed` field yet.
 *
 * No existing test file covered this component (checked: no `ContactChatbotSection.
 * test.tsx` in this tree before this one - the coordinator's "extend the existing
 * page/section test file... if one covers the recall switch" does not apply, there was
 * none to extend).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactChatbotSection from './ContactChatbotSection';

const useContactChatbotProfile = vi.fn();
const mutate = vi.fn();
const memoryMutate = vi.fn();

// Chatbot memory lane A: `chatbot_memory_level` replaces `recall_enabled`, `language`
// moved into the facts grid (`useContactChatbotMemory`) and `always_full_report` is
// dead. The empty memory fixture below keeps every test in this file - none of which
// assert on facts/conversations/open orders - rendering the same empty states those
// new cards fall back to, rather than an undefined crash.
vi.mock('../hooks/useContactChatbot', () => ({
  useContactChatbotProfile: (...a: unknown[]) => useContactChatbotProfile(...a),
  useSaveContactChatbotProfile: () => ({ mutate, isPending: false }),
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
  useSaveContactFact: () => ({ mutate: memoryMutate, isPending: false }),
  contactChatbotMemoryQueryKey: (contactId: string) => ['contact-chatbot-memory', contactId],
}));

const BASE_PROFILE = {
  chatbot_memory_level: null,
  tier: null,
  default_ledgers: [],
  stock_allowed: true,
  notify_salesman: false,
  packing_list_allowed: false,
};

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  useContactChatbotProfile.mockReset();
  mutate.mockReset();
});

afterEach(() => cleanup());

describe('ContactChatbotSection - stock checks switch (S6)', () => {
  it('renders a Stock checks switch, checked by default', () => {
    useContactChatbotProfile.mockReturnValue({ data: BASE_PROFILE, isLoading: false, isError: false });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    const toggle = screen.getByLabelText(/stock checks/i);
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveAttribute('data-state', 'checked');
  });

  it('renders the switch unchecked when the contact is denied stock checks', () => {
    useContactChatbotProfile.mockReturnValue({
      data: { ...BASE_PROFILE, stock_allowed: false },
      isLoading: false,
      isError: false,
    });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    expect(screen.getByLabelText(/stock checks/i)).toHaveAttribute('data-state', 'unchecked');
  });

  it('flipping the switch sends stock_allowed through save.mutate', () => {
    useContactChatbotProfile.mockReturnValue({ data: BASE_PROFILE, isLoading: false, isError: false });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    fireEvent.click(screen.getByLabelText(/stock checks/i));
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({ ...BASE_PROFILE, stock_allowed: false });
  });
});

/**
 * Chatbot stock ask v2, Slice S2 (contact toggles) - AC-SA205.
 * `documentation/plans/chatbot/PLAN-chatbot-stock-ask-v2-24sep.md` "S2 - Contact
 * toggles"; `chatbot-stock-ask-v2-24sep-acceptance-criteria.md` AC-SA205.
 *
 * The component ALREADY renders both "Notify salesman" and "Packing list allowed"
 * switches (Phase 1, against `contactChatbotService.ts`'s in-memory mock overlay).
 * These tests mock `useContactChatbot` directly - the hook the component actually
 * calls - bypassing that overlay entirely, so they exercise the LIVE field shape S2
 * lands on the backend (`notify_salesman` / `packing_list_allowed` as plain profile
 * fields), not the Phase 1 mock. They are expected to already be green against the
 * current component, since the switches were built in Phase 1; they pin the contract
 * so the coder cannot regress it while deleting the mock overlay in `contactChatbotService.ts`.
 */
describe('ContactChatbotSection - contact toggles (S2, AC-SA205)', () => {
  it('renders "Notify salesman" and "Packing list allowed" switches reflecting the loaded profile', () => {
    useContactChatbotProfile.mockReturnValue({
      data: { ...BASE_PROFILE, notify_salesman: true, packing_list_allowed: false },
      isLoading: false,
      isError: false,
    });
    renderWithClient(<ContactChatbotSection contactId="c1" />);

    const notify = screen.getByLabelText(/notify salesman/i);
    expect(notify).toBeInTheDocument();
    expect(notify).toHaveAttribute('data-state', 'checked');

    const packingList = screen.getByLabelText(/packing list allowed/i);
    expect(packingList).toBeInTheDocument();
    expect(packingList).toHaveAttribute('data-state', 'unchecked');
  });

  it('toggling "Notify salesman" saves the whole profile with every other field unchanged', () => {
    const loaded = {
      ...BASE_PROFILE,
      chatbot_memory_level: 'full',
      tier: 'dealer',
      stock_allowed: true,
      notify_salesman: false,
      packing_list_allowed: true,
    };
    useContactChatbotProfile.mockReturnValue({ data: loaded, isLoading: false, isError: false });
    renderWithClient(<ContactChatbotSection contactId="c1" />);

    fireEvent.click(screen.getByLabelText(/notify salesman/i));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({ ...loaded, notify_salesman: true });
  });

  it('toggling "Packing list allowed" saves the whole profile with every other field unchanged, including notify_salesman', () => {
    const loaded = {
      ...BASE_PROFILE,
      chatbot_memory_level: null,
      tier: null,
      stock_allowed: true,
      notify_salesman: true,
      packing_list_allowed: false,
    };
    useContactChatbotProfile.mockReturnValue({ data: loaded, isLoading: false, isError: false });
    renderWithClient(<ContactChatbotSection contactId="c1" />);

    fireEvent.click(screen.getByLabelText(/packing list allowed/i));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({ ...loaded, packing_list_allowed: true });
  });
});
