import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';

import { CoverageManager } from './coverage-manager';
import type { CoverageSub, TeamCoverageSub } from '../services/coverageService';

// cmdk needs ResizeObserver + scrollIntoView, absent in jsdom.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};

const useMyCoverage = vi.fn();
const useTeamCoverage = vi.fn();
const subscribeMutate = vi.fn();
const updateMutate = vi.fn();
const unsubscribeMutate = vi.fn();
const assignMutate = vi.fn();
const revokeMutate = vi.fn();

vi.mock('../hooks/useCoverage', () => ({
  useMyCoverage: (...a: unknown[]) => useMyCoverage(...a),
  useTeamCoverage: (...a: unknown[]) => useTeamCoverage(...a),
  useSubscribeCoverage: () => ({ mutate: subscribeMutate, isPending: false }),
  useUpdateCoverage: () => ({ mutate: updateMutate, isPending: false }),
  useUnsubscribeCoverage: () => ({ mutate: unsubscribeMutate, isPending: false }),
  useAssignCoverage: () => ({ mutate: assignMutate, isPending: false }),
  useRevokeCoverageById: () => ({ mutate: revokeMutate, isPending: false }),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-me' } }, status: 'authenticated' }),
}));

vi.mock('@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA', () => ({
  useVisibleUsers: () => ({
    data: [
      { id: 'u-alice', name: 'Alice', email: 'a@e.com' },
      { id: 'u-bob', name: 'Bob', email: 'b@e.com' },
    ],
    isLoading: false,
  }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mySub: CoverageSub = {
  id: 's1',
  target_user_id: 'u-bob',
  target_user_name: 'Bob',
  is_active: true,
  redirect_assignments: false,
  expires_at: null,
  created_at: new Date().toISOString(),
};

const teamSub: TeamCoverageSub = {
  id: 'tc1',
  subscriber_id: 'u-alice',
  subscriber_name: 'Alice',
  target_user_id: 'u-bob',
  target_user_name: 'Bob',
  redirect_assignments: true,
  expires_at: null,
  created_by_id: 'u-hod',
  created_by_name: 'HoD',
  assigned_by_hod: true,
  summary: 'Alice covers for Bob, who is away. Assigned by HoD. No end date (auto-assign).',
};

beforeEach(() => {
  [useMyCoverage, useTeamCoverage, subscribeMutate, updateMutate, unsubscribeMutate, assignMutate, revokeMutate].forEach(
    (m) => m.mockReset(),
  );
  useMyCoverage.mockReturnValue({ data: [], isLoading: false, error: null });
  useTeamCoverage.mockReturnValue({ data: [], isLoading: false, error: null });
});

describe('CoverageManager — non-manager', () => {
  it('coverer is fixed to "You" (no coverer picker)', () => {
    render(<CoverageManager canManageTeam={false} />);
    // Only ONE combobox (the "Covers for" picker); coverer is a static "You".
    expect(screen.getAllByRole('combobox')).toHaveLength(1);
    expect(screen.getByText('Coverer')).toBeInTheDocument();
  });

  it('Add posts self-service subscribe with the chosen target', async () => {
    render(<CoverageManager canManageTeam={false} />);
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByText('Bob'));
    fireEvent.click(screen.getByRole('button', { name: /^Add$/i }));
    await waitFor(() => expect(subscribeMutate).toHaveBeenCalled());
    expect(subscribeMutate.mock.calls[0][0]).toMatchObject({ targetUserId: 'u-bob', redirectAssignments: true });
    expect(assignMutate).not.toHaveBeenCalled();
  });

  it('lists my coverage as "You → target" and delete uses unsubscribe', async () => {
    useMyCoverage.mockReturnValue({ data: [mySub], isLoading: false, error: null });
    render(<CoverageManager canManageTeam={false} />);
    // The row renders "You → Bob" (assert via the row's remove control).
    const removeBtn = screen.getByRole('button', { name: /Remove You covering Bob/i });
    expect(removeBtn).toBeInTheDocument();
    fireEvent.click(removeBtn);
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /^Remove$/i }));
    await waitFor(() => expect(unsubscribeMutate).toHaveBeenCalled());
    expect(unsubscribeMutate.mock.calls[0][0]).toBe('u-bob'); // by target id
  });
});

describe('CoverageManager — manager', () => {
  it('coverer picker present (You + colleagues); assigning a colleague posts assign', async () => {
    render(<CoverageManager canManageTeam />);
    const combos = screen.getAllByRole('combobox');
    expect(combos).toHaveLength(2); // coverer + covered
    // Pick coverer = Alice.
    fireEvent.click(combos[0]);
    fireEvent.click(await screen.findByText('Alice'));
    // Pick covered = Bob.
    fireEvent.click(screen.getAllByRole('combobox')[1]);
    fireEvent.click((await screen.findAllByText('Bob')).at(-1)!);
    fireEvent.click(screen.getByRole('button', { name: /^Add$/i }));
    await waitFor(() => expect(assignMutate).toHaveBeenCalled());
    expect(assignMutate.mock.calls[0][0]).toMatchObject({ covererId: 'u-alice', targetUserId: 'u-bob' });
    expect(subscribeMutate).not.toHaveBeenCalled();
  });

  it('team list shows "Alice → Bob" + assigned-by badge; delete uses revoke by id', async () => {
    useTeamCoverage.mockReturnValue({ data: [teamSub], isLoading: false, error: null });
    render(<CoverageManager canManageTeam />);
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    // "Assigned by HoD" appears in both the visible badge and the sr-only summary;
    // assert the visible badge specifically.
    expect(
      screen
        .getAllByText(/Assigned by HoD/i)
        .some((el) => el.closest('[data-slot="badge"]')),
    ).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /Remove Alice covering Bob/i }));
    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /^Remove$/i }));
    await waitFor(() => expect(revokeMutate).toHaveBeenCalled());
    expect(revokeMutate.mock.calls[0][0]).toBe('tc1'); // by subscription id
  });

  it('empty state renders', () => {
    render(<CoverageManager canManageTeam />);
    expect(screen.getByText(/No active coverage yet/i)).toBeInTheDocument();
  });

  it('renders the backend role-explicit summary in the DOM (sr-only) for the AI snapshot', () => {
    useTeamCoverage.mockReturnValue({ data: [teamSub], isLoading: false, error: null });
    render(<CoverageManager canManageTeam />);
    // The canonical sentence — unambiguous about coverer vs covers-for vs assigned-by —
    // is present in the DOM (sr-only is captured by innerText / read by AT).
    expect(
      screen.getByText(
        /Alice covers for Bob, who is away\. Assigned by HoD\. No end date \(auto-assign\)\./i,
      ),
    ).toBeInTheDocument();
  });
});
