/**
 * Reserve history timestamps are UTC on the wire (`...Z` / `+00:00`, and older naive
 * strings are naive UTC too): the dialog shows them in Malaysia time, whatever the
 * machine's own time zone. Since `PLAN-oi-no-double-count-25sep.md` S0 the entries render
 * as the Reserve tab of the line's History dialog (`ReserveHistoryEntries`).
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ReserveHistoryEntries } from './ReserveLineHistoryDialog';

function renderAt(createdAt: string) {
  render(
    <ReserveHistoryEntries
      entries={[
        {
          kind: 'reserved',
          qty: '20',
          location: 'BRW',
          reason: null,
          actor_name: 'Eling',
          created_at: createdAt,
        },
      ]}
    />,
  );
}

describe('ReserveHistoryEntries timestamps', () => {
  it('renders a 2026-09-24T04:25:00Z event as 24/09/2026, 12:25 PM (MYT)', () => {
    renderAt('2026-09-24T04:25:00Z');
    expect(screen.getByText(/Eling on 24\/09\/2026, 12:25 pm/i)).toBeInTheDocument();
  });

  it('reads a +00:00 offset and an old naive UTC string the same way', () => {
    renderAt('2026-09-24T04:25:00+00:00');
    expect(screen.getByText(/24\/09\/2026, 12:25 pm/i)).toBeInTheDocument();
  });

  it('an old naive row (stored naive UTC) also shows MYT', () => {
    renderAt('2026-09-24T04:25:00');
    expect(screen.getByText(/24\/09\/2026, 12:25 pm/i)).toBeInTheDocument();
  });
});
