/**
 * LinkedComplaintsPanel / LinkedComplaintsChip - the surfaces that answer
 * "which complaints does this root cause / resolution cover?".
 *
 * Pins the three things that would silently rot: the panel filters on the right
 * field, every row links to the complaint detail page, and the empty state
 * renders instead of the section vanishing (CRUD UX standard).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const useComplaintsMock = vi.fn();
vi.mock('../complaints/hooks/useComplaints', () => ({
  useComplaints: (...a: unknown[]) => useComplaintsMock(...a),
}));

import { LinkedComplaintsPanel } from './LinkedComplaintsPanel';
import { LinkedComplaintsChip } from './LinkedComplaintsChip';

function complaint(over: Record<string, unknown> = {}) {
  return {
    id: 'cmp-1',
    complaint_number: 'CMP2026-0012',
    customer_name: 'ACME Sdn Bhd',
    delivery_order_number: 'DO-26-0441',
    complaint_date: '2026-07-01T00:00:00Z',
    status: 'approved',
    ...over,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
  return client;
}

beforeEach(() => {
  vi.clearAllMocks();
  useComplaintsMock.mockReturnValue({ data: { data: [complaint()] }, isLoading: false });
});

describe('LinkedComplaintsPanel', () => {
  it('filters on root_cause_ids when given a root cause', () => {
    renderWithClient(<LinkedComplaintsPanel rootCauseId="rc-1" />);

    expect(useComplaintsMock).toHaveBeenCalledWith(
      expect.objectContaining({
        root_cause_ids: ['rc-1'],
        resolution_ids: undefined,
      }),
    );
  });

  it('filters on resolution_ids when given a resolution', () => {
    renderWithClient(<LinkedComplaintsPanel resolutionId="res-9" />);

    expect(useComplaintsMock).toHaveBeenCalledWith(
      expect.objectContaining({
        resolution_ids: ['res-9'],
        root_cause_ids: undefined,
      }),
    );
  });

  it('renders the complaint number as a link to the complaint detail page', () => {
    renderWithClient(<LinkedComplaintsPanel rootCauseId="rc-1" />);

    const link = screen.getByRole('link', { name: 'CMP2026-0012' });
    expect(link).toHaveAttribute('href', '/complaint-management/complaints/cmp-1');
  });

  it('shows customer and DO number, and never a raw id', () => {
    renderWithClient(<LinkedComplaintsPanel rootCauseId="rc-1" />);

    expect(screen.getByText('ACME Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('DO-26-0441')).toBeInTheDocument();
    expect(screen.queryByText('cmp-1')).toBeNull();
  });

  it('falls back to a readable label when the complaint has no number', () => {
    useComplaintsMock.mockReturnValue({
      data: { data: [complaint({ complaint_number: null })] },
      isLoading: false,
    });
    renderWithClient(<LinkedComplaintsPanel rootCauseId="rc-1" />);

    expect(screen.getByRole('link', { name: 'View complaint' })).toBeInTheDocument();
  });

  it('renders an empty state with a next-step CTA, not nothing', () => {
    useComplaintsMock.mockReturnValue({ data: { data: [] }, isLoading: false });
    renderWithClient(<LinkedComplaintsPanel rootCauseId="rc-1" />);

    expect(screen.getByText('No complaints linked yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to complaints' })).toHaveAttribute(
      'href',
      '/complaint-management/complaints',
    );
  });

  it('does not show the empty state while still loading', () => {
    useComplaintsMock.mockReturnValue({ data: undefined, isLoading: true });
    renderWithClient(<LinkedComplaintsPanel rootCauseId="rc-1" />);

    expect(screen.queryByText('No complaints linked yet')).toBeNull();
  });
});

describe('LinkedComplaintsChip', () => {
  it('shows the count from the row and does not query until opened', () => {
    renderWithClient(
      <LinkedComplaintsChip
        rootCauseId="rc-1"
        label="Manufacturing Defect"
        count={6}
        detailHref="/complaint-management/complaint-root-causes/rc-1"
      />,
    );

    expect(screen.getByText('6')).toBeInTheDocument();
    expect(useComplaintsMock).not.toHaveBeenCalled();
  });

  it('opens a dialog listing the linked complaints plus a detail-page link', async () => {
    renderWithClient(
      <LinkedComplaintsChip
        rootCauseId="rc-1"
        label="Manufacturing Defect"
        count={6}
        detailHref="/complaint-management/complaint-root-causes/rc-1"
      />,
    );

    fireEvent.click(screen.getByRole('button'));

    await waitFor(() =>
      expect(
        screen.getByText('Linked complaints · Manufacturing Defect'),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole('link', { name: 'CMP2026-0012' }),
    ).toHaveAttribute('href', '/complaint-management/complaints/cmp-1');
    expect(screen.getByRole('link', { name: /Open full details/ })).toHaveAttribute(
      'href',
      '/complaint-management/complaint-root-causes/rc-1',
    );
  });

  it('stops the click so the row underneath does not also navigate', () => {
    const rowClick = vi.fn();
    renderWithClient(
      <div onClick={rowClick}>
        <LinkedComplaintsChip
          rootCauseId="rc-1"
          count={0}
          detailHref="/complaint-management/complaint-root-causes/rc-1"
        />
      </div>,
    );

    fireEvent.click(screen.getByRole('button'));
    expect(rowClick).not.toHaveBeenCalled();
  });
});
