/**
 * FILTER-MULTISELECT PR2: the AI usage page's Feature filter takes several values (OR within the
 * filter) and every panel reads the same set. The feature reaches each usage hook as a list or a
 * comma-joined string; either reads the same here. The "All AI usage" placeholder is never a value.
 * Harness mirrors page.test.tsx.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const ok = (data: unknown) => ({ data, isLoading: false, isError: false });
const useUsageSummary = vi.fn();
const useUsageByDay = vi.fn();
const useTopUsers = vi.fn();
const useRecentQueries = vi.fn();

vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: ({ title }: { title: string }) => <h1>{title}</h1> }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('../hooks/useAIUsage', () => ({
  useUsageSummary: (...a: unknown[]) => useUsageSummary(...a),
  useUsageByDay: (...a: unknown[]) => useUsageByDay(...a),
  useTopUsers: (...a: unknown[]) => useTopUsers(...a),
  useTopContacts: () => ok([]),
  useRecentQueries: (...a: unknown[]) => useRecentQueries(...a),
  useQueryDetail: () => ({ data: undefined, isLoading: false, isError: false }),
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

import AIUsagePage from './page';

const asList = (v: unknown): string[] =>
  v == null || v === '' ? [] : Array.isArray(v) ? (v as string[]) : String(v).split(',');
// the feature is the last argument of each hook that carries it (from, to[, limit], feature)
const featureOf = (mock: ReturnType<typeof vi.fn>, index: number) => {
  const calls = mock.mock.calls;
  return calls[calls.length - 1][index];
};

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
  for (const m of [useUsageSummary, useUsageByDay, useTopUsers, useRecentQueries]) m.mockReset();
  useUsageSummary.mockReturnValue(ok({ total_messages: 0, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, cost_usd: 0, unpriced_calls: 0, unknown_cache_calls: 0 }));
  useUsageByDay.mockReturnValue(ok([]));
  useTopUsers.mockReturnValue(ok([]));
  useRecentQueries.mockReturnValue(ok([]));
});
afterEach(() => cleanup());

describe('AI usage - multi Feature filter', () => {
  it('is a multi control', async () => {
    render(<AIUsagePage />);
    const box = await within(screen.getByTestId('ai-usage-feature-filter')).findByRole('listbox');
    expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two features reach every usage hook, never with the All placeholder', async () => {
    const user = userEvent.setup();
    render(<AIUsagePage />);
    const box = await within(screen.getByTestId('ai-usage-feature-filter')).findByRole('listbox');
    await user.selectOptions(box, ['ai_assistant', 'chatbot_parser']);
    await waitFor(() => expect(asList(featureOf(useUsageSummary, 2))).toEqual(['ai_assistant', 'chatbot_parser']));
    expect(asList(featureOf(useUsageByDay, 2))).toEqual(['ai_assistant', 'chatbot_parser']);
    expect(asList(featureOf(useTopUsers, 3))).toEqual(['ai_assistant', 'chatbot_parser']);
    expect(asList(featureOf(useRecentQueries, 3))).toEqual(['ai_assistant', 'chatbot_parser']);
    expect(asList(featureOf(useUsageSummary, 2))).not.toContain('__all__');
  });

  it('nothing chosen sends no feature', async () => {
    render(<AIUsagePage />);
    await within(screen.getByTestId('ai-usage-feature-filter')).findByRole('listbox');
    expect(asList(featureOf(useUsageSummary, 2))).toEqual([]);
  });
});
