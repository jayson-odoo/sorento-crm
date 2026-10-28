/**
 * FILTER-MULTISELECT PR2: the Chatbot domains Team filter takes several values and filters in the
 * browser: picking two teams shows the domains of either and hides the rest; clearing restores all.
 * Harness mirrors ChatbotDomainsList.test.tsx.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ChatbotDomain } from '../types/chatbotDomain.types';

const useChatbotDomainsQuery = vi.fn();
vi.mock('../hooks/useChatbotDomains', () => ({ useChatbotDomainsQuery: () => useChatbotDomainsQuery() }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('./ChatbotDomainModal', () => ({ default: () => null }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import ChatbotDomainsList from './ChatbotDomainsList';

const mk = (name: string, team: string): ChatbotDomain => ({
  id: `id-${name}`, name, label: `Label ${name}`, intents: [], tools: [], primary_tool: null,
  escalation_team_code: team, switch_words: [], narrowing: {}, takes_date_filter: false, reveal_key: null,
  supported: true, ladder: [], updated_at: '2026-09-01T09:00:00',
}) as ChatbotDomain;

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
  useChatbotDomainsQuery.mockReset();
  useChatbotDomainsQuery.mockReturnValue({
    data: [mk('zzt-dom-a', 'purchasing'), mk('zzt-dom-b', 'warehouse'), mk('zzt-dom-c', 'it_admin')],
    isLoading: false, isError: false,
  });
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  render(<ChatbotDomainsList />);
  await screen.findByText('zzt-dom-a');
  await user.click(screen.getByRole('button', { name: /^filters/i }));
}
const visible = (name: string) => screen.queryByText(name) !== null;

describe('Chatbot domains - multi Team filter', () => {
  it('is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await screen.findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('two teams show the domains of either and hide the rest', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox'), ['purchasing', 'warehouse']);
    await waitFor(() => expect(visible('zzt-dom-c')).toBe(false));
    expect(visible('zzt-dom-a')).toBe(true);
    expect(visible('zzt-dom-b')).toBe(true);
  });

  it('clearing the filter restores every domain', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox'), ['purchasing', 'warehouse']);
    await waitFor(() => expect(visible('zzt-dom-c')).toBe(false));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(visible('zzt-dom-c')).toBe(true));
    expect(visible('zzt-dom-a') && visible('zzt-dom-b')).toBe(true);
  });
});
