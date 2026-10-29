/**
 * FILTER-MULTISELECT PR2: the topic audit's Subject filter takes several values (OR within the
 * filter), comma-joined to the audit query. Nothing chosen sends no subject.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import TopicAuditScreen from './TopicAuditScreen';

const useTopicAuditQuery = vi.fn();
vi.mock('@/hooks/useTopicAuditQuery', () => ({ useTopicAuditQuery: (...a: unknown[]) => useTopicAuditQuery(...a) }));
vi.mock('@/hooks/useTopicAuditMutations', () => ({
  useDrawTopicAuditSample: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useSaveTopicAuditVerdict: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
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

const DATA = {
  version: 2, versions: [2], sample_size: 4, reviewed: 0,
  rates: { subject: null, topic: null, product: null },
  targets: { subject: 0.9, topic: 0.8, product: 0.95 },
  topics: [
    { code: 'inventory', label: 'Stock', parent_code: null },
    { code: 'order', label: 'Orders', parent_code: null },
    { code: 'general', label: 'General chat', parent_code: null },
  ],
  rows: [],
};
const lastArgs = () => {
  const calls = useTopicAuditQuery.mock.calls;
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
  useTopicAuditQuery.mockReset();
  useTopicAuditQuery.mockReturnValue({ data: DATA, isLoading: false, isError: false, error: null });
});
afterEach(() => cleanup());

describe('Topic audit - multi Subject filter', () => {
  it('is a multi control', async () => {
    render(<TopicAuditScreen />);
    await screen.findByText('Topic audit');
    expect((await screen.findByRole('listbox')).hasAttribute('multiple')).toBe(true);
  });

  it('two subjects go to the query comma-joined', async () => {
    const user = userEvent.setup();
    render(<TopicAuditScreen />);
    await user.selectOptions(await screen.findByRole('listbox'), ['inventory', 'general']);
    await waitFor(() => expect(lastArgs().subject).toBe('inventory,general'));
  });

  it('nothing chosen sends no subject', async () => {
    render(<TopicAuditScreen />);
    await screen.findByRole('listbox');
    expect(lastArgs().subject).toBeUndefined();
  });
});
