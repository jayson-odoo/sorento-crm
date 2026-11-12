import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AuditTrail from './AuditTrail';
import type { RecordHistoryEvent } from '@/types/recordHistory.types';

/**
 * STANDARD-HISTORY v2 (owner "ok" on mock v2, 10 Nov 2026): the ONE history component is the
 * existing Audit Trail. Given plain `entries` (a record's history endpoint) it shows each as two
 * lines - one sentence, then when and who - with the lines only on "Show N lines", and at most
 * one control: a search box once there are more than 10 entries. No filters, no badges, no grid.
 * Data: the OI-2611-0019 story, names masked.
 */
const NINE = [
  'CKS1050',
  'CKSW015',
  'SRT61-CR',
  'SRTHD122',
  'SRTSH22512-N',
  'SRTWC286-SH-NEW',
  'SRTWT167',
  'SRTWT2219',
].map((item, i) => ({ row_id: `r${i}`, so_line_no: i + 1, item_code: item, qty: 4, change: 'Confirmed → To confirm' }));
NINE.push({ row_id: 'r8', so_line_no: 9, item_code: 'SRTSP131', qty: 4, change: 'Done by hand → To confirm' });

const STORY: RecordHistoryEvent[] = [
  {
    id: 'link',
    kind: 'linked',
    at: '2026-11-10T02:52:00',
    actor: 'Automatic',
    title: 'PO 202611-S0027 linked to SRTSP131',
    lines: [{ row_id: 'r8', so_line_no: 9, item_code: 'SRTSP131', qty: 4, change: 'Linked 4 to PO 202611-S0027' }],
  },
  {
    id: 'unconfirm',
    kind: 'unconfirmed',
    at: '2026-11-09T09:15:53',
    actor: 'J*** (Purchasing)',
    title: 'Unconfirmed 9 lines, back to To confirm',
    lines: NINE,
  },
  {
    id: 'confirm',
    kind: 'confirmed',
    at: '2026-11-09T09:15:45',
    actor: 'J*** (Purchasing)',
    title: 'Confirmed SRTSP131',
    lines: [{ row_id: 'r8', so_line_no: 9, item_code: 'SRTSP131', qty: 4, change: 'To confirm → Confirmed' }],
  },
  {
    id: 'raise',
    kind: 'raised',
    at: '2026-11-02T09:31:00',
    actor: 'A*** (CS)',
    title: 'Raised 13 lines',
    lines: [],
  },
];

function renderTrail(props: Partial<React.ComponentProps<typeof AuditTrail>> = {}) {
  return render(
    <AuditTrail
      title="History"
      entries={STORY}
      isLoading={false}
      isError={false}
      onRetry={() => {}}
      {...(props as object)}
    />,
  );
}

function entry(title: string) {
  return screen.getByText(title).closest('[data-audit-entry]') as HTMLElement;
}

describe('AuditTrail with plain entries (STANDARD-HISTORY v2)', () => {
  it('shows each entry as one sentence, then when and who, newest first, in the Audit Trail card', () => {
    renderTrail();
    expect(screen.getByText('History')).toBeInTheDocument();
    const items = screen.getAllByTestId('audit-action').map((el) => el.textContent);
    expect(items).toEqual([
      'PO 202611-S0027 linked to SRTSP131',
      'Unconfirmed 9 lines, back to To confirm',
      'Confirmed SRTSP131',
      'Raised 13 lines',
    ]);
    const unconfirm = entry('Unconfirmed 9 lines, back to To confirm');
    expect(unconfirm).toHaveTextContent('09/11/2026');
    expect(unconfirm).toHaveTextContent('by J*** (Purchasing)');
    expect(entry('PO 202611-S0027 linked to SRTSP131')).toHaveTextContent('Automatic');
  });

  it('shows seconds only where two entries share a minute (the Confirm and the Unconfirm 8 s later)', () => {
    renderTrail();
    expect(entry('Unconfirmed 9 lines, back to To confirm')).toHaveTextContent(/5:15:53/);
    expect(entry('Confirmed SRTSP131')).toHaveTextContent(/5:15:45/);
    expect(entry('Raised 13 lines')).not.toHaveTextContent(/5:31:00/);
    expect(entry('Raised 13 lines')).toHaveTextContent(/5:31/);
  });

  it('has no filters, no badges and no grid; lines appear only on "Show N lines"', () => {
    renderTrail();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    const unconfirm = entry('Unconfirmed 9 lines, back to To confirm');
    expect(within(unconfirm).queryAllByTestId('audit-change-line')).toHaveLength(0);
    fireEvent.click(within(unconfirm).getByRole('button', { name: 'Show 9 lines' }));
    const lines = within(unconfirm).getAllByTestId('audit-change-line').map((l) => l.textContent);
    expect(lines).toHaveLength(9);
    expect(lines[8]).toBe('SRTSP131: Done by hand → To confirm');
    fireEvent.click(within(unconfirm).getByRole('button', { name: 'Hide' }));
    expect(within(unconfirm).queryAllByTestId('audit-change-line')).toHaveLength(0);
  });

  it('a one-line entry shows its line with no toggle; an entry with no lines offers none', () => {
    renderTrail();
    const confirm = entry('Confirmed SRTSP131');
    expect(within(confirm).queryByRole('button')).not.toBeInTheDocument();
    expect(within(confirm).getByTestId('audit-change-line')).toHaveTextContent('SRTSP131: To confirm → Confirmed');
    expect(within(entry('Raised 13 lines')).queryByRole('button')).not.toBeInTheDocument();
  });

  it('past 10 entries, one search box; a match keeps a batch whole and shows its matching line', () => {
    const many: RecordHistoryEvent[] = [
      ...STORY,
      ...Array.from({ length: 8 }, (_, i) => ({
        id: `x${i}`,
        kind: 'linked',
        at: `2026-10-0${i + 1}T01:00:00`,
        actor: 'Automatic',
        title: `PO 2026-OLD-${i} linked to CKSW015`,
        lines: [],
      })),
    ];
    renderTrail({ entries: many });
    const search = screen.getByRole('textbox', { name: 'Search history' });
    fireEvent.change(search, { target: { value: 'srtsp131' } });
    const items = screen.getAllByTestId('audit-action').map((el) => el.textContent);
    expect(items).toEqual([
      'PO 202611-S0027 linked to SRTSP131',
      'Unconfirmed 9 lines, back to To confirm',
      'Confirmed SRTSP131',
    ]);
    const unconfirm = entry('Unconfirmed 9 lines, back to To confirm');
    expect(within(unconfirm).getAllByTestId('audit-change-line').map((l) => l.textContent)).toEqual([
      'SRTSP131: Done by hand → To confirm',
    ]);
    fireEvent.change(search, { target: { value: 'J***' } });
    expect(screen.getAllByTestId('audit-action')).toHaveLength(2);
  });

  it('empty: a heading and a hint, no button; error: Retry', () => {
    const { unmount } = renderTrail({ entries: [] });
    expect(screen.getByRole('heading', { name: 'No history yet' })).toBeInTheDocument();
    expect(screen.getByText('Changes to this record appear here.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    unmount();
    const onRetry = vi.fn();
    renderTrail({ entries: [], isError: true, onRetry });
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
