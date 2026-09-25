/**
 * `PLAN-oi-decision-trail-ui.md` (round 2, AC-DT-5/AC-DT-10). The service call is mocked
 * so `useDecisionTrail`'s own `useQuery` resolves synchronously against a fake, never a
 * real `fetch` - this is a UI test, not a wire test (that lives in `tests/test_decision_
 * trail.py` and `orderInquiryReserveService`'s own layering).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

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
});
