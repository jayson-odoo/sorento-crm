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

// AC-MEM057 (round 3): stubbed as a deterministic native `<select>` so the memory
// context level options/values/clearable-ness are asserted directly, the same
// pattern `StockVisibilitySection.test.tsx` uses for the same real component.
vi.mock('@/components/common/SearchableSelect', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/components/common/SearchableSelect')>();
  type Props = Parameters<typeof actual.SearchableSelect>[0];
  const Stub = ({ value, onChange, options, placeholder, disabled, clearable }: Props) => (
    <select
      aria-label={placeholder ?? 'select'}
      data-clearable={clearable === undefined ? 'unset' : String(clearable)}
      value={value ?? ''}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
  return { ...actual, SearchableSelect: (props: Props) => <Stub {...props} /> };
});

const BASE_PROFILE = {
  chatbot_memory_level: null,
  tier: null,
  default_ledgers: [],
  stock_allowed: true,
  notify_salesman: false,
  packing_list_allowed: false,
  eta_offset_applied: true,
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

/**
 * AC-MEM057 (round 3 UAC, merged 5b110df8): the Contact page "Memory context level"
 * select's option set is renamed to the round 3 level values (`past` -> `episodes`),
 * stays clearable, and its `onChange` payload is asserted against
 * `contactChatbotService.memoryLevel.test.ts` (this file mocks the save HOOK, so it
 * cannot see the outgoing HTTP body key `memory_level` renamed from
 * `chatbot_memory_level` - that is pinned at the service layer instead).
 */
describe('ContactChatbotSection - memory context level select (AC-MEM057, round 3)', () => {
  function levelSelect() {
    return screen.getByLabelText('(follow the system default)') as HTMLSelectElement;
  }

  it('offers exactly Off / This conversation / Past conversations / Full memory, with values off/conversation/episodes/full', () => {
    useContactChatbotProfile.mockReturnValue({ data: BASE_PROFILE, isLoading: false, isError: false });
    renderWithClient(<ContactChatbotSection contactId="c1" />);

    const options = Array.from(levelSelect().options).map((o) => ({
      value: o.value,
      label: o.textContent,
    }));
    expect(options).toEqual([
      { value: 'off', label: 'Off' },
      { value: 'conversation', label: 'This conversation' },
      { value: 'episodes', label: 'Past conversations' },
      { value: 'full', label: 'Full memory' },
    ]);
  });

  it('is clearable', () => {
    useContactChatbotProfile.mockReturnValue({ data: BASE_PROFILE, isLoading: false, isError: false });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    expect(levelSelect()).toHaveAttribute('data-clearable', 'true');
  });

  it('picking "Past conversations" saves chatbot_memory_level as "episodes", not "past"', () => {
    useContactChatbotProfile.mockReturnValue({ data: BASE_PROFILE, isLoading: false, isError: false });
    renderWithClient(<ContactChatbotSection contactId="c1" />);

    fireEvent.change(levelSelect(), { target: { value: 'episodes' } });

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({ ...BASE_PROFILE, chatbot_memory_level: 'episodes' });
  });
});

/**
 * Issue #1328 (AC-EO6): the per-contact ETA offset switch, default on, saved with the
 * rest of the profile unchanged.
 */
describe('ContactChatbotSection - ETA buffer days switch (#1328)', () => {
  it('renders the switch checked by default', () => {
    useContactChatbotProfile.mockReturnValue({ data: BASE_PROFILE, isLoading: false, isError: false });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    expect(screen.getByLabelText(/eta buffer days/i)).toHaveAttribute('data-state', 'checked');
  });

  it('renders unchecked for a contact told the exact ETA', () => {
    useContactChatbotProfile.mockReturnValue({
      data: { ...BASE_PROFILE, eta_offset_applied: false },
      isLoading: false,
      isError: false,
    });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    expect(screen.getByLabelText(/eta buffer days/i)).toHaveAttribute('data-state', 'unchecked');
  });

  it('flipping it saves eta_offset_applied with every other field unchanged', () => {
    const loaded = { ...BASE_PROFILE, notify_salesman: true, packing_list_allowed: true };
    useContactChatbotProfile.mockReturnValue({ data: loaded, isLoading: false, isError: false });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    fireEvent.click(screen.getByLabelText(/eta buffer days/i));
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({ ...loaded, eta_offset_applied: false });
  });
});

/**
 * ESCALATION-CONTROL (owner, 30 Sep 2026): "Can escalate to customer service" is
 * inherit / allow / block. Inherit is the cleared select, whose placeholder names the
 * value the contact's access types give it.
 */
describe('ContactChatbotSection - Can escalate to a person', () => {
  const DEALER = {
    ...BASE_PROFILE,
    escalation_allowed: null,
    escalation_allowed_inherited: false,
    escalation_allowed_inherited_from: 'Sorento Dealer',
  };

  it('shows the inherited value when the contact has no override', () => {
    useContactChatbotProfile.mockReturnValue({ data: DEALER, isLoading: false, isError: false });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    // The stub is a native <select> with no blank option, so an empty value cannot be
    // read back; the placeholder is what names the inherited value.
    const select = screen.getByLabelText('(inherit: blocked via Sorento Dealer)');
    expect(select).toHaveAttribute('data-clearable', 'true');
  });

  it('names the access type that allowed it (owner hand test, Mr Loo)', () => {
    useContactChatbotProfile.mockReturnValue({
      data: {
        ...DEALER,
        escalation_allowed_inherited: true,
        escalation_allowed_inherited_from: 'Sorento Office',
      },
      isLoading: false,
      isError: false,
    });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    expect(screen.getByText('Inherited: allowed via Sorento Office')).toBeInTheDocument();
    expect(screen.getByLabelText('(inherit: allowed via Sorento Office)')).toBeInTheDocument();
  });

  it('with an override, the line still shows what it would inherit', () => {
    useContactChatbotProfile.mockReturnValue({
      data: { ...DEALER, escalation_allowed: false },
      isLoading: false,
      isError: false,
    });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    expect(screen.getByText('Own setting · inherited: blocked via Sorento Dealer')).toBeInTheDocument();
  });

  it('allow saves true, block saves false, clearing saves null (inherit)', () => {
    useContactChatbotProfile.mockReturnValue({
      data: { ...DEALER, escalation_allowed: true },
      isLoading: false,
      isError: false,
    });
    renderWithClient(<ContactChatbotSection contactId="c1" />);
    const select = screen.getByLabelText('(inherit: blocked via Sorento Dealer)');
    expect(select).toHaveValue('allow');
    fireEvent.change(select, { target: { value: 'block' } });
    fireEvent.change(select, { target: { value: '' } });
    expect(mutate.mock.calls.map((c) => c[0].escalation_allowed)).toEqual([false, null]);
    expect(mutate.mock.calls[0][0]).toEqual({ ...DEALER, escalation_allowed: false });
  });
});
