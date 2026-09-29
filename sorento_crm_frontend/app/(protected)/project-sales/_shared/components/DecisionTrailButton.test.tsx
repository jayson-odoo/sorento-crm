/**
 * `PLAN-oi-decision-trail-ui.md` (round 2, AC-DT-5/AC-DT-10). The service call is mocked
 * so `useDecisionTrail`'s own `useQuery` resolves synchronously against a fake, never a
 * real `fetch` - this is a UI test, not a wire test (that lives in `tests/test_decision_
 * trail.py` and `orderInquiryReserveService`'s own layering).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getDecisionTrail = vi.fn();
vi.mock('../services/orderInquiryReserveService', async () => {
  const actual = await vi.importActual<
    typeof import('../services/orderInquiryReserveService')
  >('../services/orderInquiryReserveService');
  return { ...actual, getDecisionTrail: (...args: unknown[]) => getDecisionTrail(...args) };
});

import { DecisionTrailButton } from './DecisionTrailButton';

function renderButton(props: Partial<React.ComponentProps<typeof DecisionTrailButton>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DecisionTrailButton coreLineId="core-line-1" itemCode="CB6622-PP" {...props} />
    </QueryClientProvider>,
  );
}

describe('DecisionTrailButton', () => {
  beforeEach(() => {
    getDecisionTrail.mockReset();
  });

  it('renders nothing for a row that names no core sales-order line', () => {
    render(<DecisionTrailButton coreLineId={null} itemCode="CB6622-PP" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('fetches nothing until clicked, then opens the dialog scoped to that core line', async () => {
    getDecisionTrail.mockResolvedValueOnce([
      { kind: 'confirmed', actor_name: 'Nurain', at: '2026-09-25T01:20:34Z', detail: 'Revision 1 · Buy 10' },
    ]);
    renderButton();

    expect(getDecisionTrail).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /decision trail/i }));

    expect(getDecisionTrail).toHaveBeenCalledWith('core-line-1');
    await waitFor(() => expect(screen.getByText(/Confirmed.*Revision 1/)).toBeInTheDocument());
    expect(screen.getByText('Decision trail - CB6622-PP')).toBeInTheDocument();
  });

  it('shows the empty state for a core line with nothing recorded', async () => {
    getDecisionTrail.mockResolvedValueOnce([]);
    renderButton({ coreLineId: 'core-line-empty' });

    fireEvent.click(screen.getByRole('button', { name: /decision trail/i }));

    await waitFor(() =>
      expect(screen.getByText('No trail recorded yet.')).toBeInTheDocument(),
    );
  });

  /**
   * S1 (review round 3): `trail.data ?? []` alone read BOTH a loading state and a
   * failed fetch as "No trail recorded yet." - the empty state claims the read
   * succeeded and simply found nothing, which is not true of either.
   */
  it('S1: shows a skeleton while the read is in flight, never the empty state', async () => {
    let resolve!: (value: unknown[]) => void;
    getDecisionTrail.mockReturnValueOnce(
      new Promise((r) => {
        resolve = r;
      }),
    );
    renderButton({ coreLineId: 'core-line-slow' });

    fireEvent.click(screen.getByRole('button', { name: /decision trail/i }));

    expect(await screen.findByTestId('decision-trail-loading')).toBeInTheDocument();
    expect(screen.queryByText('No trail recorded yet.')).not.toBeInTheDocument();

    resolve([]);
    await waitFor(() =>
      expect(screen.getByText('No trail recorded yet.')).toBeInTheDocument(),
    );
  });

  it('S1: shows the error message on a failed fetch, never the empty state', async () => {
    getDecisionTrail.mockRejectedValueOnce(new Error('Failed to load that decision trail'));
    renderButton({ coreLineId: 'core-line-broken' });

    fireEvent.click(screen.getByRole('button', { name: /decision trail/i }));

    await waitFor(() =>
      expect(screen.getByText('Failed to load that decision trail')).toBeInTheDocument(),
    );
    expect(screen.queryByText('No trail recorded yet.')).not.toBeInTheDocument();
  });

  /**
   * S3 (review round 3): guards the query key - two different rows (each its own
   * `DecisionTrailButton` instance, the real shape: a worklist/board renders one per
   * line, never one shared instance) must fetch their OWN core line, never a cached
   * answer belonging to the other.
   */
  it('S3: two different core lines each fetch their own trail, never a shared cache entry', async () => {
    getDecisionTrail.mockResolvedValueOnce([]).mockResolvedValueOnce([]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { unmount } = render(
      <QueryClientProvider client={client}>
        <DecisionTrailButton coreLineId="core-line-a" itemCode="CODE-A" />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /decision trail/i }));
    await waitFor(() => expect(getDecisionTrail).toHaveBeenCalledWith('core-line-a'));
    unmount();

    render(
      <QueryClientProvider client={client}>
        <DecisionTrailButton coreLineId="core-line-b" itemCode="CODE-B" />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /decision trail/i }));
    await waitFor(() => expect(getDecisionTrail).toHaveBeenCalledWith('core-line-b'));

    expect(getDecisionTrail).toHaveBeenCalledTimes(2);
  });
});
