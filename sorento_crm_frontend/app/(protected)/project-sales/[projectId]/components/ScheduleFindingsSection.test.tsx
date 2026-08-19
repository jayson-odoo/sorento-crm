/**
 * The (PO, schedule) pair's own findings - none of which name a PO line, so none of which
 * belong to any one order the pair drafted. The binding rule under test: nothing renders
 * once every finding here is cleared, unlike the order's own Blocking/Warnings cards.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ProjectSalesOrderFinding } from '../../_shared/types/projectSalesOrder.types';
import { ScheduleFindingsSection } from './ScheduleFindingsSection';

const OPEN: ProjectSalesOrderFinding = {
  id: 'bf1',
  severity: 'hard',
  code: 'schedule_over',
  detail: 'The schedule asks for 890 of SRTWT7445-LV, which is not on this purchase order at all.',
  line_id: null,
  line_no: null,
};

const CLEARED: ProjectSalesOrderFinding = {
  id: 'bf2',
  severity: 'warn',
  code: 'phase_unmatched',
  detail: "Schedule phase 'Level 9' belongs to another project.",
  line_id: null,
  line_no: null,
  acknowledged_by_name: 'Eling',
  acknowledged_reason: 'Confirmed, dropping that column next revision.',
  acknowledged_at: '2026-08-19T09:00:00',
};

describe('ScheduleFindingsSection', () => {
  it('renders nothing when there is nothing open', () => {
    const { container } = render(
      <ScheduleFindingsSection findings={[CLEARED]} canEdit onAcknowledge={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing at all with an empty list', () => {
    const { container } = render(
      <ScheduleFindingsSection findings={[]} canEdit onAcknowledge={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('names the pair rather than any one order, and counts only the open ones', () => {
    render(<ScheduleFindingsSection findings={[OPEN, CLEARED]} canEdit onAcknowledge={vi.fn()} />);

    expect(screen.getByText('Schedule / PO findings')).toBeInTheDocument();
    expect(screen.getByText('1 on this purchase order')).toBeInTheDocument();
    expect(screen.getByText(/890 of SRTWT7445-LV/)).toBeInTheDocument();
    // The cleared one is still shown, with its reason, not hidden.
    expect(screen.getByText(/dropping that column/)).toBeInTheDocument();
    expect(screen.getByText('Cleared by Eling')).toBeInTheDocument();
  });

  it('hides the clear action when the reader cannot edit', () => {
    render(<ScheduleFindingsSection findings={[OPEN]} canEdit={false} onAcknowledge={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Clear with a reason' })).not.toBeInTheDocument();
  });

  it('records a reason through the same acknowledge dialog an order finding uses', async () => {
    const onAcknowledge = vi.fn().mockResolvedValue(undefined);
    render(<ScheduleFindingsSection findings={[OPEN]} canEdit onAcknowledge={onAcknowledge} />);

    fireEvent.click(screen.getByRole('button', { name: 'Clear with a reason' }));
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'Confirmed against the printed total.' },
    });
    // A hard finding, like an order's own, asks for a second confirmation before it writes.
    fireEvent.click(screen.getByRole('button', { name: 'Override' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Override and record' }));

    await waitFor(() =>
      expect(onAcknowledge).toHaveBeenCalledWith('bf1', 'Confirmed against the printed total.'),
    );
  });
});
