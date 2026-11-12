import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RecordHistoryEvent } from '@/types/recordHistory.types';

/**
 * STANDARD-HISTORY wave 2 (AC-SH-W2-6): one wrapper for both sales order pages. It reads the
 * project or SCM history and renders `AuditTrail` entries mode, titled "History".
 * Data: masked real shapes (SO329258 Unconfirm, SO401624 refused Confirm).
 */
const projectSpy = vi.hoisted(() => vi.fn());
const scmSpy = vi.hoisted(() => vi.fn());

vi.mock('@/services/salesOrderHistoryService', () => ({
  getProjectSalesOrderHistory: (...args: unknown[]) => projectSpy(...args),
  getScmSalesOrderHistory: (...args: unknown[]) => scmSpy(...args),
}));

import SalesOrderHistory from './SalesOrderHistory';

const EVENTS: RecordHistoryEvent[] = [
  {
    id: 'e2',
    kind: 'confirm_refused',
    at: '2026-10-22T17:25:00',
    actor: 'C*** (CS)',
    title: 'Confirm refused: 1 line cannot be confirmed. Nothing was written.',
    lines: [{ row_id: 'r9', so_line_no: 1, item_code: 'SRTSA-SS', qty: null, change: 'Qty 10 → 8' }],
  },
  {
    id: 'e1',
    kind: 'unconfirmed',
    at: '2026-09-23T08:00:00',
    actor: 'J*** (Purchasing)',
    title: 'Unconfirmed 4 lines, back to To confirm',
    lines: ['B2155-NL-BLUE', 'C-FH14', 'CSA150', 'CKS1050'].map((item, i) => ({
      row_id: `r${i}`,
      so_line_no: i + 1,
      item_code: item,
      qty: 4,
      change: 'Confirmed → To confirm',
    })),
  },
];

function renderIt(source: 'project' | 'scm', id = 'so-1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SalesOrderHistory source={source} id={id} />
    </QueryClientProvider>,
  );
}

describe('SalesOrderHistory', () => {
  beforeEach(() => {
    projectSpy.mockReset();
    scmSpy.mockReset();
  });

  it('project source reads the project history and shows each entry title under "History"', async () => {
    projectSpy.mockResolvedValue({ events: EVENTS });
    renderIt('project', 'pso-7');
    expect(
      await screen.findByText('Confirm refused: 1 line cannot be confirmed. Nothing was written.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Unconfirmed 4 lines, back to To confirm')).toBeInTheDocument();
    expect(screen.getByText('History')).toBeInTheDocument();
    expect(projectSpy).toHaveBeenCalledWith('pso-7');
    expect(scmSpy).not.toHaveBeenCalled();
  });

  it('scm source reads the SCM history', async () => {
    scmSpy.mockResolvedValue({ events: EVENTS });
    renderIt('scm', 'so-3');
    expect(await screen.findByText('Unconfirmed 4 lines, back to To confirm')).toBeInTheDocument();
    expect(scmSpy).toHaveBeenCalledWith('so-3');
    expect(projectSpy).not.toHaveBeenCalled();
  });

  it('empty: "No history yet" and no button', async () => {
    projectSpy.mockResolvedValue({ events: [] });
    renderIt('project');
    expect(await screen.findByText('No history yet')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('error: "Could not load the history" with Retry that reads again', async () => {
    projectSpy.mockRejectedValueOnce(new Error('boom'));
    renderIt('project');
    expect(await screen.findByText('Could not load the history')).toBeInTheDocument();
    projectSpy.mockResolvedValueOnce({ events: EVENTS });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() =>
      expect(screen.getByText('Unconfirmed 4 lines, back to To confirm')).toBeInTheDocument(),
    );
    expect(projectSpy).toHaveBeenCalledTimes(2);
  });
});
