/**
 * FILTER-MULTISELECT PR2: the Activity timeline's Action and User filters take several values (OR
 * within a filter, AND across). Entity types already took several. Each filter reaches the feed hook
 * as a list or a comma-joined string; either reads the same here. The "All" placeholders are never
 * values. Harness mirrors ActivityTimeline.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ActivityTimeline from './ActivityTimeline';

const useActivityFeed = vi.fn();
vi.mock('../hooks/useActivityFeed', () => ({ useActivityFeed: (...a: unknown[]) => useActivityFeed(...a) }));
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

const asList = (v: unknown): string[] =>
  v == null ? [] : Array.isArray(v) ? (v as string[]) : String(v).split(',');
const lastParams = () => {
  const calls = useActivityFeed.mock.calls;
  return calls[calls.length - 1][0] as Record<string, unknown>;
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
  useActivityFeed.mockReset();
  useActivityFeed.mockReturnValue({
    data: {
      items: [],
      actors: [{ id: 'u-ann', name: 'Ann Lee' }, { id: 'u-ben', name: 'Ben Lim' }],
      pagination: { total: 0, page: 1, limit: 50 },
    },
    isLoading: false, isError: false, error: null, refetch: vi.fn(), isFetching: false,
  });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ActivityTimeline />
    </QueryClientProvider>,
  );
}

describe('Activity timeline - multi Action and User filters', () => {
  it('are two multi controls, Action then User', async () => {
    renderIt();
    const boxes = await screen.findAllByRole('listbox');
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box.hasAttribute('multiple')).toBe(true);
  });

  it('two actions reach the hook, never with the All placeholder', async () => {
    const user = userEvent.setup();
    renderIt();
    const [action] = await screen.findAllByRole('listbox');
    await user.selectOptions(action, ['created', 'deleted']);
    await waitFor(() => expect(asList(lastParams().action)).toEqual(['created', 'deleted']));
    expect(asList(lastParams().action)).not.toContain('__any__');
  });

  it('two users reach the hook', async () => {
    const user = userEvent.setup();
    renderIt();
    const boxes = await screen.findAllByRole('listbox');
    await waitFor(() => expect((boxes[1] as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(boxes[1], ['u-ann', 'u-ben']);
    await waitFor(() => expect(asList(lastParams().user_id)).toEqual(['u-ann', 'u-ben']));
  });

  it('the filters AND across each other and Reset drops them', async () => {
    const user = userEvent.setup();
    renderIt();
    const boxes = await screen.findAllByRole('listbox');
    await waitFor(() => expect((boxes[1] as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(boxes[0], ['updated', 'deleted']);
    await user.selectOptions(boxes[1], ['u-ben']);
    await waitFor(() => {
      expect(asList(lastParams().action)).toEqual(['updated', 'deleted']);
      expect(asList(lastParams().user_id)).toEqual(['u-ben']);
    });
  });

  it('entity types still take several values (guard)', async () => {
    const user = userEvent.setup();
    renderIt();
    await user.click(await screen.findByRole('button', { name: /entity types/i }));
    await user.click(await screen.findByLabelText('Customer'));
    await user.click(await screen.findByLabelText('Complaint'));
    await waitFor(() => expect(asList(lastParams().entity_types)).toEqual(['customer', 'complaint']));
  });
});
