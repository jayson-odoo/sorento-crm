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

vi.mock('../hooks/useContactChatbot', () => ({
  useContactChatbotProfile: (...a: unknown[]) => useContactChatbotProfile(...a),
  useSaveContactChatbotProfile: () => ({ mutate, isPending: false }),
}));

const BASE_PROFILE = {
  recall_enabled: false,
  tier: null,
  language: null,
  default_ledgers: [],
  always_full_report: false,
  stock_allowed: true,
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
