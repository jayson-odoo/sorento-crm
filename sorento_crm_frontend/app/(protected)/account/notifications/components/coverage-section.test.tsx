import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import { CoverageSection } from './coverage-section';
import type { CoverageSub } from '../services/coverageService';

const useMyCoverage = vi.fn();
const subscribeMutate = vi.fn();
const unsubscribeMutate = vi.fn();

vi.mock('../hooks/useCoverage', () => ({
  useMyCoverage: (...a: unknown[]) => useMyCoverage(...a),
  useSubscribeCoverage: () => ({ mutate: subscribeMutate, isPending: false }),
  useUnsubscribeCoverage: () => ({ mutate: unsubscribeMutate, isPending: false }),
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
  expires_at: null,
  created_at: new Date().toISOString(),
};

beforeEach(() => {
  useMyCoverage.mockReset();
  subscribeMutate.mockReset();
  unsubscribeMutate.mockReset();
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
});
