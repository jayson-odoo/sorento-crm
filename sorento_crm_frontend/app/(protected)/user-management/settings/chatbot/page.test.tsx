/**
 * Settings -> Chatbot (AC-809, AC-810, issue #679).
 *
 * RED, written before `./page.tsx` exists. Prescribes the contract the coder
 * builds against, mirroring the precedent at `../chatbot-media/page.test.tsx`:
 * the hooks module is mocked directly (never `fetch` / `apiFetch`), so each test
 * can drive query/mutation state precisely.
 *
 * Expected hooks module: `./hooks/useChatbotSettings.ts`, exporting:
 *   - `useChatbotLanes()`      -> query over GET /settings/chatbot-lanes,
 *                                 resolving to `ChatbotLane[]` = `{kind, built}[]`
 *   - `useChatbotSettings()`   -> query over the existing GET /settings, picking
 *                                 the five chatbot fields into `ChatbotSettings`
 *   - `useSaveChatbotSettings()` -> mutation over POST /settings/general with a
 *                                 `ChatbotSettings` body
 *
 * Expected service module: `./services/chatbotSettingsService.ts`, exporting the
 * two types below and the three fetchers the hooks wrap.
 *
 * ```ts
 * export interface ChatbotLane { kind: string; built: boolean }
 * export interface ChatbotSettings {
 *   chatbot_completed_lanes: string[];
 *   chatbot_stock_denial_enabled: boolean;
 *   chatbot_business_lane_enabled: boolean;
 *   chatbot_ordering_enabled: boolean;
 *   chatbot_unsupported_domains: string[];
 * }
 * ```
 *
 * No feature-explanation copy in the UI (cursor rule); a "not built" hint on a
 * disabled checkbox is a STATE label, not an explainer, and stays.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

Element.prototype.scrollIntoView = vi.fn();
(Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const mockLanesQuery = vi.fn();
const mockSettingsQuery = vi.fn();
const mockMutation = vi.fn();

vi.mock('./hooks/useChatbotSettings', () => ({
  useChatbotLanes: () => mockLanesQuery(),
  useChatbotSettings: () => mockSettingsQuery(),
  useSaveChatbotSettings: () => mockMutation(),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

import ChatbotSettingsPage from './page';
import type {
  ChatbotLane,
  ChatbotSettings,
} from './services/chatbotSettingsService';

const ALL_KINDS = [
  'access_denied',
  'escalate_offer',
  'out_of_scope',
  'ideate',
  'offer_hold',
  'escalation_declined',
  'check_promotion',
  'low_signal',
  'clarify_menu',
  'not_supported',
  'stock_denied',
  'demand_qty',
  'business_query',
];

function lanes(overrides: Partial<Record<string, boolean>> = {}): ChatbotLane[] {
  return ALL_KINDS.map((kind) => ({
    kind,
    built: overrides[kind] ?? true,
  }));
}

function settings(overrides: Partial<ChatbotSettings> = {}): ChatbotSettings {
  return {
    chatbot_completed_lanes: [],
    chatbot_stock_denial_enabled: false,
    chatbot_business_lane_enabled: false,
    chatbot_ordering_enabled: false,
    chatbot_unsupported_domains: ['goods_receive', 'spo_allocation'],
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatbotSettingsPage />
    </QueryClientProvider>,
  );
}

const saveButton = () => screen.getByRole('button', { name: /save/i });

beforeEach(() => {
  mockLanesQuery.mockReset();
  mockSettingsQuery.mockReset();
  mockMutation.mockReset();
  mockLanesQuery.mockReturnValue({ data: lanes(), isLoading: false, isError: false });
  mockSettingsQuery.mockReturnValue({ data: settings(), isLoading: false, isError: false });
  mockMutation.mockReturnValue({ isPending: false, mutate: vi.fn() });
});

afterEach(() => cleanup());

describe('ChatbotSettingsPage - lane checkboxes (AC-809)', () => {
  it('renders a checkbox per branch kind, checked according to the current completed lanes', () => {
    mockSettingsQuery.mockReturnValue({
      data: settings({ chatbot_completed_lanes: ['low_signal', 'out_of_scope'] }),
      isLoading: false,
      isError: false,
    });
    renderPage();

    for (const kind of ALL_KINDS) {
      const checkbox = screen.getByRole('checkbox', { name: new RegExp(kind, 'i') });
      const expected = kind === 'low_signal' || kind === 'out_of_scope' ? 'true' : 'false';
      expect(checkbox.getAttribute('aria-checked')).toBe(expected);
    }
  });

  it('disables a checkbox and shows a "not built" hint for a kind whose built flag is false', () => {
    mockLanesQuery.mockReturnValue({
      data: lanes({ business_query: false }),
      isLoading: false,
      isError: false,
    });
    renderPage();

    const checkbox = screen.getByRole('checkbox', { name: /business_query/i });
    expect(checkbox).toBeDisabled();
    expect(screen.getByText(/not built/i)).toBeInTheDocument();
  });

  it('leaves a built kind enabled with no "not built" hint attached to it', () => {
    renderPage();

    const checkbox = screen.getByRole('checkbox', { name: /low_signal/i });
    expect(checkbox).not.toBeDisabled();
  });
});

describe('ChatbotSettingsPage - the three switches (AC-810)', () => {
  it('reflects stock denial, business lane and ordering from the current settings', () => {
    mockSettingsQuery.mockReturnValue({
      data: settings({
        chatbot_stock_denial_enabled: true,
        chatbot_business_lane_enabled: false,
        chatbot_ordering_enabled: false,
      }),
      isLoading: false,
      isError: false,
    });
    renderPage();

    expect(screen.getByLabelText(/stock denial/i).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByLabelText(/business lane/i).getAttribute('aria-checked')).toBe('false');
    expect(screen.getByLabelText(/ordering/i).getAttribute('aria-checked')).toBe('false');
  });
});

describe('ChatbotSettingsPage - unsupported domains list editor (AC-809, D5)', () => {
  it('renders every configured domain as an editable list item', () => {
    mockSettingsQuery.mockReturnValue({
      data: settings({ chatbot_unsupported_domains: ['goods_receive', 'spo_allocation'] }),
      isLoading: false,
      isError: false,
    });
    renderPage();

    expect(screen.getByText('goods_receive')).toBeInTheDocument();
    expect(screen.getByText('spo_allocation')).toBeInTheDocument();
  });

  it('removing a domain and saving excludes it from the payload', () => {
    const mutate = vi.fn();
    mockMutation.mockReturnValue({ isPending: false, mutate });
    mockSettingsQuery.mockReturnValue({
      data: settings({ chatbot_unsupported_domains: ['goods_receive', 'spo_allocation'] }),
      isLoading: false,
      isError: false,
    });
    renderPage();

    const domainRow = screen.getByText('spo_allocation').closest('li,div') as HTMLElement;
    fireEvent.click(within(domainRow).getByRole('button', { name: /remove/i }));
    fireEvent.click(saveButton());

    expect(mutate).toHaveBeenCalledTimes(1);
    const [payload] = mutate.mock.calls[0];
    expect(payload.chatbot_unsupported_domains).toEqual(['goods_receive']);
  });
});

describe('ChatbotSettingsPage - Save payload (AC-809, AC-810)', () => {
  it('calls the mutation with the exact current draft, snake_case, on every chatbot field', () => {
    const mutate = vi.fn();
    mockMutation.mockReturnValue({ isPending: false, mutate });
    mockLanesQuery.mockReturnValue({ data: lanes(), isLoading: false, isError: false });
    mockSettingsQuery.mockReturnValue({
      data: settings({
        chatbot_completed_lanes: ['low_signal'],
        chatbot_stock_denial_enabled: true,
        chatbot_business_lane_enabled: false,
        chatbot_ordering_enabled: false,
        chatbot_unsupported_domains: ['goods_receive', 'spo_allocation'],
      }),
      isLoading: false,
      isError: false,
    });
    renderPage();

    // Check one more lane before saving, so the payload proves the draft is
    // read back, not just echoed from the query.
    fireEvent.click(screen.getByRole('checkbox', { name: /clarify_menu/i }));
    fireEvent.click(saveButton());

    expect(mutate).toHaveBeenCalledTimes(1);
    const [payload] = mutate.mock.calls[0];
    expect(payload).toEqual({
      chatbot_completed_lanes: expect.arrayContaining(['low_signal', 'clarify_menu']),
      chatbot_stock_denial_enabled: true,
      chatbot_business_lane_enabled: false,
      chatbot_ordering_enabled: false,
      chatbot_unsupported_domains: ['goods_receive', 'spo_allocation'],
    });
    expect(payload.chatbot_completed_lanes).toHaveLength(2);
  });
});

describe('ChatbotSettingsPage - ordering confirm dialog (AC-810)', () => {
  it('switching ordering on opens an AlertDialog whose text mentions 410, never window.confirm', () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    mockSettingsQuery.mockReturnValue({
      data: settings({ chatbot_ordering_enabled: false }),
      isLoading: false,
      isError: false,
    });
    renderPage();

    fireEvent.click(screen.getByLabelText(/ordering/i));

    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByRole('alertdialog').textContent).toMatch(/410/);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('cancelling the ordering confirm dialog leaves ordering off', () => {
    mockSettingsQuery.mockReturnValue({
      data: settings({ chatbot_ordering_enabled: false }),
      isLoading: false,
      isError: false,
    });
    renderPage();

    fireEvent.click(screen.getByLabelText(/ordering/i));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.getByLabelText(/ordering/i).getAttribute('aria-checked')).toBe('false');
  });
});

describe('ChatbotSettingsPage - loading and error states', () => {
  it('shows a loading state while either query is pending', () => {
    mockLanesQuery.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderPage();

    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('shows an error state, not an infinite loader, when a query fails', () => {
    mockSettingsQuery.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    renderPage();

    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.getByText(/could not be loaded/i)).toBeInTheDocument();
  });
});
