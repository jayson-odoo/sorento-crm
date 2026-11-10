import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RecordHistory, type RecordHistoryEvent } from './RecordHistory';

/**
 * STANDARD-HISTORY wave 1 (AC-SH-B8 to B11): the standard History body, built from the SO
 * History drawer's own pieces. Data: the OI-2611-0019 story, names masked.
 */
const UNCONFIRM_LINES = [
  ['CKS1050', 1],
  ['CKSW015', 2],
  ['SRT61-CR', 3],
  ['SRTHD122', 4],
  ['SRTSH22512-N', 5],
  ['SRTWC286-SH-NEW', 6],
  ['SRTWT167', 7],
  ['SRTWT2219', 8],
  ['SRTSP131', 9],
].map(([item, no]) => ({
  row_id: `row-${no}`,
  so_line_no: no as number,
  item_code: item as string,
  qty: 4,
  change: 'Confirmed -> To confirm',
}));

const EVENTS: RecordHistoryEvent[] = [
  {
    id: 'link-1',
    kind: 'linked',
    at: '2026-11-10T02:52:00',
    actor: 'Automatic',
    title: '202611-S0027 linked to 1 line',
    lines: [{ row_id: 'row-9', so_line_no: 9, item_code: 'SRTSP131', qty: 4, change: 'Linked 4 to 202611-S0027' }],
  },
  {
    id: 'audit-unconfirm',
    kind: 'unconfirmed',
    at: '2026-11-09T09:15:53',
    actor: 'J*** (Purchasing)',
    title: 'Unconfirmed 9 lines',
    lines: UNCONFIRM_LINES,
  },
  {
    id: 'audit-confirm',
    kind: 'confirmed',
    at: '2026-11-09T09:15:45',
    actor: 'J*** (Purchasing)',
    title: 'Confirmed 1 line',
    lines: [{ row_id: 'row-9', so_line_no: 9, item_code: 'SRTSP131', qty: 4, change: 'To confirm -> Confirmed' }],
  },
  {
    id: 'raise-1',
    kind: 'raised',
    at: '2026-11-02T09:31:00',
    actor: 'A*** (CS)',
    title: 'Raised 13 lines',
    lines: [],
  },
];

const LABELS = {
  raised: 'Raised',
  confirmed: 'Confirmed',
  unconfirmed: 'Unconfirmed',
  linked: 'Linked',
};

function renderHistory(props: Partial<React.ComponentProps<typeof RecordHistory>> = {}) {
  return render(
    <RecordHistory
      events={EVENTS}
      kindLabels={LABELS}
      isLoading={false}
      isError={false}
      onRetry={() => {}}
      {...props}
    />,
  );
}

describe('RecordHistory (STANDARD-HISTORY wave 1)', () => {
  it('shows every event newest first, grouped by dd/mm/yyyy day, with its kind badge and actor (AC-SH-B8)', () => {
    renderHistory();
    const timeline = screen.getByTestId('history-timeline');
    const text = timeline.textContent ?? '';
    expect(text.indexOf('10/11/2026')).toBeLessThan(text.indexOf('09/11/2026'));
    expect(text.indexOf('09/11/2026')).toBeLessThan(text.indexOf('02/11/2026'));
    expect(text.indexOf('Unconfirmed 9 lines')).toBeLessThan(text.indexOf('Confirmed 1 line'));
    const unconfirm = screen.getByTestId('history-event-audit-unconfirm');
    expect(within(unconfirm).getByText('Unconfirmed', { selector: '[data-slot="badge"], span' })).toBeInTheDocument();
    expect(within(unconfirm).getByText('J*** (Purchasing)')).toBeInTheDocument();
  });

  it('a batch press is ONE event; its title opens the lines table, one row per line (AC-SH-B10)', () => {
    renderHistory();
    const unconfirm = screen.getByTestId('history-event-audit-unconfirm');
    expect(within(unconfirm).queryByRole('table')).not.toBeInTheDocument();
    fireEvent.click(within(unconfirm).getByRole('button', { name: /Unconfirmed 9 lines/ }));
    const table = within(unconfirm).getByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 9);
    expect(within(table).getByText('SRTWC286-SH-NEW')).toBeInTheDocument();
    expect(within(table).getAllByText('Confirmed -> To confirm')).toHaveLength(9);
  });

  it('a Product filter keeps the batch as one event showing only the matching line (AC-SH-B9)', () => {
    renderHistory();
    fireEvent.click(screen.getByRole('combobox', { name: 'Product' }));
    fireEvent.click(screen.getByRole('option', { name: 'SRTSP131' }));
    // The raise lists no lines, so a Product filter hides it, the drawer's rule.
    expect(screen.queryByTestId('history-event-raise-1')).not.toBeInTheDocument();
    const unconfirm = screen.getByTestId('history-event-audit-unconfirm');
    fireEvent.click(within(unconfirm).getByRole('button', { name: /Unconfirmed 9 lines/ }));
    const rows = within(within(unconfirm).getByRole('table')).getAllByRole('row');
    expect(rows).toHaveLength(2);
    expect(rows[1]).toHaveTextContent('SRTSP131');
  });

  it('a User filter narrows to that person (AC-SH-B9)', () => {
    renderHistory();
    fireEvent.click(screen.getByRole('combobox', { name: 'User' }));
    fireEvent.click(screen.getByRole('option', { name: 'Automatic' }));
    expect(screen.getByTestId('history-event-link-1')).toBeInTheDocument();
    expect(screen.queryByTestId('history-event-audit-unconfirm')).not.toBeInTheDocument();
  });

  it('without line filters there is no Product or Line select (AC-SH-B12)', () => {
    renderHistory({ lineFilters: false });
    expect(screen.queryByRole('combobox', { name: 'Product' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Line' })).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'User' })).toBeInTheDocument();
  });

  it('empty: a heading and a hint, no button; error: Retry (AC-SH-B11)', () => {
    const { unmount } = renderHistory({ events: [] });
    expect(screen.getByRole('heading', { name: 'No history' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
    unmount();
    const onRetry = vi.fn();
    renderHistory({ events: [], isError: true, onRetry });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
