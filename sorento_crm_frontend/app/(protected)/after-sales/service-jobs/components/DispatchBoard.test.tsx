/**
 * AFTER-SALES-P1 fix round 1 (S-8, S-1): the board shows its error with Try again, and the top
 * section is "Waiting for a date".
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>,
}));

const board = vi.fn();
vi.mock('../hooks/useServiceJobs', () => ({ useDispatchBoard: () => board() }));

import DispatchBoard from './DispatchBoard';

const job = { id: 'j-1', job_number: 'SV26/11-0001', status: 'proposed', status_label: 'Proposed', city: 'Ipoh', scheduled_from: null };

beforeEach(() => board.mockReset());

describe('DispatchBoard', () => {
  it('shows the error and retries instead of a skeleton forever', () => {
    const refetch = vi.fn();
    board.mockReturnValue({ data: undefined, isLoading: false, isError: true, error: new Error('Boom'), refetch });
    render(<DispatchBoard />);
    expect(screen.getByRole('alert').textContent).toMatch(/Boom/);
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(refetch).toHaveBeenCalled();
  });

  it('shows Waiting for a date above the technician columns', () => {
    board.mockReturnValue({
      data: { day: '2026-11-20', waiting: [job], columns: [{ technician_id: null, technician_name: 'Unassigned', jobs: [] }] },
      isLoading: false, isError: false, refetch: vi.fn(),
    });
    render(<DispatchBoard />);
    expect(screen.getByText('Waiting for a date')).toBeInTheDocument();
    expect(screen.getByText('SV26/11-0001')).toBeInTheDocument();
    expect(screen.queryByText(/stalled/i)).toBeNull();
  });
});
