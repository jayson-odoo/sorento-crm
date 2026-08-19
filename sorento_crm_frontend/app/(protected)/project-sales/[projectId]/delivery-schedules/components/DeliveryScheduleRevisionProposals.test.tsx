/**
 * P6 section 9.7b/c - one re-date proposal per card, its cells, the Accept confirm, decided
 * pills and the empty state. Every card renders even with nothing proposed.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { RevisionProposal } from '../../../_shared/types/deliverySchedule.types';
import { DeliveryScheduleRevisionProposals } from './DeliveryScheduleRevisionProposals';

function proposal(overrides: Partial<RevisionProposal> = {}): RevisionProposal {
  return {
    product_id: 'p1',
    item_code: 'SRT382-6',
    note_text: 'ONLY FOR FLOOR TRAP TO BE DELIVER IN 2026, START FROM 23/7/2026',
    page_no: 7,
    state: 'proposed',
    decided_by: null,
    decided_at: null,
    cells: [
      {
        phase_id: 'ph1',
        phase_label: 'Level 2 & 7',
        qty: '72',
        old_date: '2027-01-07',
        new_date: '2026-07-23',
      },
      {
        phase_id: 'ph2',
        phase_label: 'Level 8 & 10',
        qty: '48',
        old_date: '2027-01-21',
        new_date: '2026-08-06',
      },
    ],
    ...overrides,
  };
}

describe('DeliveryScheduleRevisionProposals', () => {
  it('says nothing was proposed, without hiding the section', () => {
    render(
      <DeliveryScheduleRevisionProposals
        proposals={[]}
        canDecide
        pendingIndex={null}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.getByText('Re-dating proposals')).toBeInTheDocument();
    expect(screen.getByText('No re-dating proposed')).toBeInTheDocument();
  });

  it('titles the card with the item, the phase count, the first date and the note, and lists the cells was -> now', () => {
    render(
      <DeliveryScheduleRevisionProposals
        proposals={[
          proposal({
            cells: [
              ...proposal().cells,
              {
                phase_id: 'ph3',
                phase_label: 'Common area',
                qty: '30',
                old_date: '2027-03-01',
                new_date: '2026-09-15',
              },
            ],
          }),
        ]}
        canDecide
        pendingIndex={null}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(
      screen.getByText(
        "SRT382-6 - re-date 3 phases from 23/07/2026, keeping the document's own gaps",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('From the note on page 7 and the highlighted cells'),
    ).toBeInTheDocument();
    expect(screen.getByText('07/01/2027')).toBeInTheDocument();
    expect(screen.getByText('23/07/2026')).toBeInTheDocument();
  });

  it('accepts only after the confirm dialog names the line and the verb', () => {
    const onAccept = vi.fn();
    render(
      <DeliveryScheduleRevisionProposals
        proposals={[proposal()]}
        canDecide
        pendingIndex={null}
        onAccept={onAccept}
        onReject={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    expect(onAccept).not.toHaveBeenCalled();

    const dialog = within(screen.getByRole('dialog'));
    expect(
      dialog.getByText(
        "Re-date SRT382-6's 2 phases? The amendment will propose ADVANCE per line.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(dialog.getByRole('button', { name: 'Accept' }));
    expect(onAccept).toHaveBeenCalledWith(0);
  });

  it('rejects with one click, no confirm needed', () => {
    const onReject = vi.fn();
    render(
      <DeliveryScheduleRevisionProposals
        proposals={[proposal()]}
        canDecide
        pendingIndex={null}
        onAccept={vi.fn()}
        onReject={onReject}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    expect(onReject).toHaveBeenCalledWith(0);
  });

  it('shows the accepted pill, and offers no buttons once decided', () => {
    render(
      <DeliveryScheduleRevisionProposals
        proposals={[
          proposal({ state: 'accepted', decided_by: 'u1', decided_at: '2026-08-19T02:00:00' }),
        ]}
        canDecide
        pendingIndex={null}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    // The pill states the fact, never the raw user id (no UUIDs in the UI).
    expect(screen.getByText('Accepted 19/08/2026')).toBeInTheDocument();
    expect(screen.queryByText('u1')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });

  it('shows a bare Rejected pill', () => {
    render(
      <DeliveryScheduleRevisionProposals
        proposals={[proposal({ state: 'rejected' })]}
        canDecide
        pendingIndex={null}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.getByText('Rejected')).toBeInTheDocument();
  });

  it('disables both buttons once the version can no longer be edited', () => {
    render(
      <DeliveryScheduleRevisionProposals
        proposals={[proposal()]}
        canDecide={false}
        pendingIndex={null}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Accept' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
  });

  it('says the fortnight cadence when every gap agrees', () => {
    render(
      <DeliveryScheduleRevisionProposals
        proposals={[
          proposal({
            cells: [
              { phase_id: 'ph1', phase_label: 'A', qty: '1', old_date: '2026-07-01', new_date: '2026-07-01' },
              { phase_id: 'ph2', phase_label: 'B', qty: '1', old_date: '2026-07-15', new_date: '2026-07-15' },
              { phase_id: 'ph3', phase_label: 'C', qty: '1', old_date: '2026-07-29', new_date: '2026-07-29' },
            ],
          }),
        ]}
        canDecide
        pendingIndex={null}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.getByText(/keeping the fortnight cadence/)).toBeInTheDocument();
  });
});
