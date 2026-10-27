/**
 * FILTER-MULTISELECT PR2 review: the Subject multi control has an accessible name, so a screen reader
 * (and a test) finds it by its label.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

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

beforeEach(() => {
  useTopicAuditQuery.mockReset();
  useTopicAuditQuery.mockReturnValue({ data: DATA, isLoading: false, isError: false, error: null });
});
afterEach(() => cleanup());

describe('Topic audit - Subject control', () => {
  it('is reachable by its label', async () => {
    render(<TopicAuditScreen />);
    await screen.findByText('Topic audit');
    expect(screen.getByLabelText('Subject')).toBeInTheDocument();
  });
});
