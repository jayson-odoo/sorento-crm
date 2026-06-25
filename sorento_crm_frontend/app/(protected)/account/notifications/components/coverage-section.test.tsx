import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import { CoverageSection } from './coverage-section';
import type { CoverageSub } from '../services/coverageService';

const useMyCoverage = vi.fn();
const subscribeMutate = vi.fn();
const unsubscribeMutate = vi.fn();
const updateMutate = vi.fn();

vi.mock('../hooks/useCoverage', () => ({
  useMyCoverage: (...a: unknown[]) => useMyCoverage(...a),
  useSubscribeCoverage: () => ({ mutate: subscribeMutate, isPending: false }),
  useUnsubscribeCoverage: () => ({ mutate: unsubscribeMutate, isPending: false }),
  useUpdateCoverage: () => ({ mutate: updateMutate, isPending: false }),
}));

vi.mock('@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA', () => ({
  useVisibleUsers: () => ({
    data: [{ id: 'u-charissa', name: 'Charissa', email: 'c@e.com' }],
    isLoading: false,
  }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const sub: CoverageSub = {
  id: 's1',
  target_user_id: 'u-charissa',
  target_user_name: 'Charissa',
  is_active: true,
  redirect_assignments: true,
  expires_at: null,
  created_at: new Date().toISOString(),
};

beforeEach(() => {
  useMyCoverage.mockReset();
  subscribeMutate.mockReset();
  unsubscribeMutate.mockReset();
  updateMutate.mockReset();
});

describe('CoverageSection', () => {
  it('loading state', () => {
    useMyCoverage.mockReturnValue({ data: [], isLoading: true, error: null });
    render(<CoverageSection />);
    expect(screen.getByText('Coverage')).toBeInTheDocument();
  });

  it('empty state renders with a CTA', () => {
    useMyCoverage.mockReturnValue({ data: [], isLoading: false, error: null });
    render(<CoverageSection />);
    expect(screen.getByText(/not covering for anyone yet/i)).toBeInTheDocument();
  });

  it('error state', () => {
    useMyCoverage.mockReturnValue({ data: [], isLoading: false, error: new Error('boom') });
    render(<CoverageSection />);
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('lists coverage rows by name (no UUIDs)', () => {
    useMyCoverage.mockReturnValue({ data: [sub], isLoading: false, error: null });
    render(<CoverageSection />);
    expect(screen.getByText('Charissa')).toBeInTheDocument();
    expect(screen.queryByText('u-charissa')).not.toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('Remove opens confirm dialog then unsubscribes', async () => {
    useMyCoverage.mockReturnValue({ data: [sub], isLoading: false, error: null });
    render(<CoverageSection />);
    fireEvent.click(screen.getByRole('button', { name: /Stop covering for Charissa/i }));
    await waitFor(() => expect(screen.getByText('Confirm delete')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /^Remove$/i }));
    expect(unsubscribeMutate).toHaveBeenCalledWith('u-charissa', expect.anything());
  });

  it('Add button is disabled until a colleague is picked', () => {
    useMyCoverage.mockReturnValue({ data: [], isLoading: false, error: null });
    render(<CoverageSection />);
    expect(screen.getByRole('button', { name: /^Add$/i })).toBeDisabled();
  });

  // ── tz-safety: expires_at is a calendar DATE, never round-tripped through Date() ──
  // A naive backend timestamp "2026-06-25T00:00:00" (no Z) must NOT shift -1 day in
  // UTC+8. Derive from the yyyy-mm-dd prefix only.
  const naiveSub: CoverageSub = {
    ...sub,
    id: 's-tz',
    expires_at: '2026-06-25T00:00:00',
  };

  it('displays the "Until" date from the yyyy-mm-dd prefix without a -1-day shift', () => {
    useMyCoverage.mockReturnValue({ data: [naiveSub], isLoading: false, error: null });
    render(<CoverageSection />);
    // dd/mm/yyyy, the SAME calendar day as the backend value (25, not 24).
    expect(screen.getByText('Until 25/06/2026')).toBeInTheDocument();
    expect(screen.queryByText('Until 24/06/2026')).not.toBeInTheDocument();
  });

  it('edit date-input is the same calendar day (yyyy-mm-dd), idempotent round-trip', () => {
    useMyCoverage.mockReturnValue({ data: [naiveSub], isLoading: false, error: null });
    render(<CoverageSection />);
    fireEvent.click(screen.getByRole('button', { name: /Edit coverage end date for Charissa/i }));
    const input = screen.getByLabelText('Coverage end date for Charissa') as HTMLInputElement;
    // Native <input type="date"> value is yyyy-mm-dd; must equal the backend prefix.
    expect(input.value).toBe('2026-06-25');
  });

  it('handles a Z-suffixed midnight UTC timestamp by its date prefix too', () => {
    useMyCoverage.mockReturnValue({
      data: [{ ...naiveSub, id: 's-z', expires_at: '2026-12-31T00:00:00Z' }],
      isLoading: false,
      error: null,
    });
    render(<CoverageSection />);
    expect(screen.getByText('Until 31/12/2026')).toBeInTheDocument();
  });
});
