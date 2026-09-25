/**
 * `PLAN-oi-decision-trail-ui.md` (round 2, AC-DT-5/AC-DT-10) - pure presentation, the same
 * shape as `ReserveLineHistoryDialog.test.tsx` beside it.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DecisionTrailDialog } from './DecisionTrailDialog';
import type { DecisionTrailEntry } from '../../../_shared/services/orderInquiryReserveService';

describe('DecisionTrailDialog', () => {
  it('renders every kind of entry, newest first, with the actor and the date', () => {
    const entries: DecisionTrailEntry[] = [
      {
        kind: 'confirmed',
        actor_name: 'Nurain',
        at: '2026-09-25T01:20:34Z',
        detail: 'Revision 1 · Buy 10',
      },
      {
        kind: 'saved',
        actor_name: 'Farah',
        at: '2026-09-25T02:00:00Z',
        detail: 'Amended · Buy 3',
      },
      {
        kind: 'reconfirmed',
        actor_name: 'Dara',
        at: '2026-09-25T01:20:33Z',
        detail: 'OI-2609-0731 · qty 20',
      },
      {
        kind: 'sheet',
        actor_name: null,
        at: null,
        detail: 'OI-2005-0012 · qty 5',
      },
      {
        kind: 'planning_change',
        actor_name: null,
        at: '2026-08-01T00:00:00Z',
        detail: 'Was 2026-07-01',
      },
    ];

    render(
      <DecisionTrailDialog open onOpenChange={() => {}} itemCode="CB6622-PP" entries={entries} />,
    );

    expect(screen.getByText('Decision trail - CB6622-PP')).toBeInTheDocument();
    expect(screen.getByText(/Confirmed.*Revision 1/)).toBeInTheDocument();
    expect(screen.getByText(/Nurain on/)).toBeInTheDocument();
    expect(screen.getByText(/Saved.*Amended/)).toBeInTheDocument();
    expect(screen.getByText(/Reconfirmed.*OI-2609-0731/)).toBeInTheDocument();
    // A `sheet` mark carries no name or date (AC-DT-6): "Unknown", no "on <date>".
    const sheetLine = screen.getByText(/Sheet.*OI-2005-0012/);
    const sheetCard = sheetLine.closest('div')?.parentElement;
    expect(sheetCard?.textContent).toContain('Unknown');
    expect(sheetCard?.textContent).not.toMatch(/Unknown on/);
    expect(screen.getByText(/Planning change.*Was 2026-07-01/)).toBeInTheDocument();
  });

  it('shows the empty state when nothing has been recorded yet', () => {
    render(
      <DecisionTrailDialog open onOpenChange={() => {}} itemCode="CB6622-PP" entries={[]} />,
    );

    expect(screen.getByText('No trail recorded yet.')).toBeInTheDocument();
  });

  it('titles the dialog without an item code when none is given', () => {
    render(<DecisionTrailDialog open onOpenChange={() => {}} itemCode={null} entries={[]} />);

    expect(screen.getByText('Decision trail')).toBeInTheDocument();
  });
});
