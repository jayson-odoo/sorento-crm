import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import MemberMarketSegmentEditor from './MemberMarketSegmentEditor';

const useMemberMarketSegments = vi.fn();
const useMarketSegments = vi.fn();
const setMutate = vi.fn();

vi.mock('@/app/(protected)/user-management/market-segments/hooks/useMarketSegments', () => ({
  useMemberMarketSegments: (...a: unknown[]) => useMemberMarketSegments(...a),
  useMarketSegments: (...a: unknown[]) => useMarketSegments(...a),
  useSetMemberMarketSegments: () => ({ mutate: setMutate, isPending: false }),
}));

const CATALOG = [
  { code: 'retail', name: 'Retail', description: null, is_active: true, sort_order: 1 },
  { code: 'project', name: 'Project', description: null, is_active: true, sort_order: 2 },
];

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** Opens the editor dialog, then the multiselect menu inside it. */
function openPicker() {
  fireEvent.click(screen.getByLabelText(/edit market segments/i));
  fireEvent.click(document.querySelector('[data-slot="searchable-multi-select-trigger"]')!);
}

beforeEach(() => {
  useMemberMarketSegments.mockReset();
  useMarketSegments.mockReset();
  setMutate.mockReset();
  useMarketSegments.mockReturnValue({ data: CATALOG, isLoading: false });
  Element.prototype.scrollIntoView = vi.fn();
  (Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
});

afterEach(() => cleanup());

describe('MemberMarketSegmentEditor', () => {
  it('shows "Serves all" when the member has no segments', () => {
    useMemberMarketSegments.mockReturnValue({ data: [], isLoading: false });
    renderWithClient(<MemberMarketSegmentEditor teamId="t1" userId="u1" />);
    expect(screen.getByText(/serves all/i)).toBeInTheDocument();
  });

  it('renders the served segments as badges (both = both shown)', () => {
    useMemberMarketSegments.mockReturnValue({ data: ['retail', 'project'], isLoading: false });
    renderWithClient(<MemberMarketSegmentEditor teamId="t1" userId="u1" />);
    expect(screen.getByText('Retail')).toBeInTheDocument();
    expect(screen.getByText('Project')).toBeInTheDocument();
  });

  it('persists the selected segments on save', () => {
    useMemberMarketSegments.mockReturnValue({ data: ['retail'], isLoading: false });
    renderWithClient(<MemberMarketSegmentEditor teamId="t1" userId="u1" />);
    openPicker();
    fireEvent.click(screen.getByRole('option', { name: 'Project' }));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(setMutate).toHaveBeenCalledTimes(1);
    expect(setMutate.mock.calls[0][0]).toEqual(['retail', 'project']);
  });

  it('still lets a stale tag be cleared when the catalogue is empty', () => {
    useMemberMarketSegments.mockReturnValue({ data: ['retail'], isLoading: false });
    useMarketSegments.mockReturnValue({ data: [], isLoading: false });
    renderWithClient(<MemberMarketSegmentEditor teamId="t1" userId="u1" />);
    openPicker();
    expect(screen.getByText(/no market segments configured/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('option', { name: 'retail' }));
    const save = screen.getByRole('button', { name: /^save$/i });
    expect(save).not.toBeDisabled();
    fireEvent.click(save);
    expect(setMutate.mock.calls[0][0]).toEqual([]);
  });
});
