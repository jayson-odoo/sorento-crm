/**
 * FILTER-MULTISELECT PR2: the Chatbot status words Domain filter takes several values and filters in
 * the browser: picking two domains shows the words of either and hides the rest; clearing restores
 * all. Harness mirrors ChatbotStatusWordsList.test.tsx.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ChatbotStatusWord } from '../types/chatbotStatusWord.types';

const useChatbotStatusWordsQuery = vi.fn();
vi.mock('../hooks/useChatbotStatusWords', () => ({
  useChatbotStatusWordsQuery: () => useChatbotStatusWordsQuery(),
}));
vi.mock('@/app/(protected)/system-management/chatbot-domains/hooks/useChatbotDomains', () => ({
  useChatbotDomainsQuery: () => ({
    data: [
      { name: 'sales', label: 'sales' },
      { name: 'stock', label: 'stock' },
      { name: 'orders', label: 'orders' },
    ],
  }),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('./ChatbotStatusWordModal', () => ({ default: () => null }));
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

import ChatbotStatusWordsList from './ChatbotStatusWordsList';

const mk = (value: string, domain: string): ChatbotStatusWord => ({
  id: `id-${value}`, domain, value, label: `label ${value}`, trigger_words: [], sort_order: 1,
  prompt_lists: [], updated_at: '2026-09-30T09:00:00',
}) as ChatbotStatusWord;

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
  useChatbotStatusWordsQuery.mockReset();
  useChatbotStatusWordsQuery.mockReturnValue({
    data: [mk('zzt_word_a', 'sales'), mk('zzt_word_b', 'stock'), mk('zzt_word_c', 'orders')],
    isLoading: false, isError: false,
  });
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  render(<ChatbotStatusWordsList />);
  await screen.findByText('zzt_word_a');
  await user.click(screen.getByRole('button', { name: /^filters/i }));
}
const visible = (name: string) => screen.queryByText(name) !== null;

describe('Chatbot status words - multi Domain filter', () => {
  it('is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await screen.findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('two domains show the words of either and hide the rest', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByRole('listbox'), ['sales', 'stock']);
    await waitFor(() => expect(visible('zzt_word_c')).toBe(false));
    expect(visible('zzt_word_a') && visible('zzt_word_b')).toBe(true);
  });

  it('deselecting every domain restores all the words', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const box = await screen.findByRole('listbox');
    await user.selectOptions(box, ['sales', 'stock']);
    await waitFor(() => expect(visible('zzt_word_c')).toBe(false));
    await user.deselectOptions(box, ['sales', 'stock']);
    await waitFor(() => expect(visible('zzt_word_c')).toBe(true));
  });
});
