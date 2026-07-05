import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactMarketSegmentSection from './ContactMarketSegmentSection';

const useContactMarketSegments = vi.fn();
const useMarketSegments = vi.fn();
const setMutate = vi.fn();

vi.mock('@/app/(protected)/user-management/market-segments/hooks/useMarketSegments', () => ({
  useContactMarketSegments: (...a: unknown[]) => useContactMarketSegments(...a),
  useMarketSegments: (...a: unknown[]) => useMarketSegments(...a),
  useSetContactMarketSegments: () => ({ mutate: setMutate, isPending: false }),
}));

const CATALOG = [
  { code: 'retail', name: 'Retail', description: null, is_active: true, sort_order: 1 },
  { code: 'project', name: 'Project', description: null, is_active: true, sort_order: 2 },
];

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  useContactMarketSegments.mockReset();
  useMarketSegments.mockReset();
  setMutate.mockReset();
  useMarketSegments.mockReturnValue({ data: CATALOG, isLoading: false });
  Element.prototype.scrollIntoView = vi.fn();
  (Element.prototype as unknown as { hasPointerCapture: unknown }).hasPointerCapture = vi.fn();
});

afterEach(() => cleanup());

describe('ContactMarketSegmentSection', () => {
  it('renders the empty state when the contact has no segment', () => {
    useContactMarketSegments.mockReturnValue({ data: [], isLoading: false });
    renderWithClient(<ContactMarketSegmentSection contactId="c1" />);
    expect(screen.getByText(/no market segment — matches all cs members/i)).toBeInTheDocument();
  });

  it('renders badges for assigned segments (human-readable names)', () => {
    useContactMarketSegments.mockReturnValue({ data: ['retail'], isLoading: false });
    renderWithClient(<ContactMarketSegmentSection contactId="c1" />);
    expect(screen.getByText('Retail')).toBeInTheDocument();
  });

  it('adds a segment without a confirm and persists', () => {
    useContactMarketSegments.mockReturnValue({ data: ['retail'], isLoading: false });
    renderWithClient(<ContactMarketSegmentSection contactId="c1" />);
    fireEvent.click(screen.getByLabelText(/edit market segment/i));
    fireEvent.click(screen.getByLabelText('Project'));
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(setMutate).toHaveBeenCalledTimes(1);
    expect(setMutate.mock.calls[0][0]).toEqual(['retail', 'project']);
  });

  it('requires a confirm before unassigning a segment', () => {
    useContactMarketSegments.mockReturnValue({ data: ['retail', 'project'], isLoading: false });
    renderWithClient(<ContactMarketSegmentSection contactId="c1" />);
    fireEvent.click(screen.getByLabelText(/edit market segment/i));
    fireEvent.click(screen.getByLabelText('Retail')); // uncheck
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    // No immediate mutation — confirmation must appear first.
    expect(setMutate).not.toHaveBeenCalled();
    expect(screen.getByText(/this will unassign retail/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^confirm$/i }));
    expect(setMutate).toHaveBeenCalledTimes(1);
    expect(setMutate.mock.calls[0][0]).toEqual(['project']);
  });
});
