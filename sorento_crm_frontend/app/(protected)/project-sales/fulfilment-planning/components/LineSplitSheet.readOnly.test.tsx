/**
 * OI-SPLIT-VIEW round 4 (UAC E1, E2): `LineSplitSheet` takes `readOnly`. Same columns, same
 * block layout and REMARK words as the edit sheet, with no grip, no "N left" chip, no Balance
 * cell, no "+ Split", no remove x, no inputs or date pickers, no click-to-edit cells and no
 * keyboard editing. Red until the prop exists (today every control renders).
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LineSplitSheet, type SheetHandlers } from './LineSplitSheet';
import { fromPayload, sortLines } from '../lib/lineSplitModel';
import { ownerSavedCase, receivingCase } from '@/test-mocks/lineSplitSheetKit';

function handlers(): SheetHandlers {
  return {
    open: vi.fn(), qty: vi.fn(), date: vi.fn(), remark: vi.fn(),
    add: vi.fn(), remove: vi.fn(), fieldBlur: vi.fn(),
  };
}

function renderSheet(payload: ReturnType<typeof ownerSavedCase>, only: number[]) {
  const all = sortLines(fromPayload(payload as never));
  const lines = all.filter((l) => only.includes(l.lineNo as number));
  const h = handlers();
  const utils = render(
    <LineSplitSheet
      readOnly
      lines={lines}
      allLines={all}
      savedLines={all}
      soNumber="SO417636"
      soDate="2026-09-03"
      openLineIds={new Set()}
      drag={null}
      overTarget={null}
      flashLineId={null}
      handlers={h}
    />,
  );
  return { ...utils, h, table: screen.getByRole('table', { name: 'Split delivery sheet' }) };
}

describe('LineSplitSheet readOnly: same sheet, no controls (E1, E2)', () => {
  it('keeps the edit sheet columns in order, minus the blank grip and remove columns and Balance', () => {
    const { table } = renderSheet(ownerSavedCase(), [480, 752]);
    const heads = Array.from(table.querySelectorAll('thead th')).map((th) => (th.textContent ?? '').trim());
    expect(heads).toEqual([
      'Line', 'SO date', 'S/O no', 'Item code', 'Location', 'Qty', 'New qty',
      'Delivery date', 'New date', 'Change quantity', 'Change date', 'Remark',
    ]);
  });

  it('draws one tbody per listed line', () => {
    renderSheet(ownerSavedCase(), [480, 752]);
    expect(screen.getAllByTestId(/^split-line-/).map((el) => el.getAttribute('data-testid'))).toEqual([
      'split-line-480', 'split-line-752',
    ]);
  });

  it('shows the change words where the edit view shows them, and the AutoCount extra row', () => {
    const { table } = renderSheet(ownerSavedCase(), [480, 752]);
    const b480 = within(screen.getByTestId('split-line-480')).getByText('ADVANCE');
    expect(b480).toBeInTheDocument();
    expect(within(screen.getByTestId('split-line-480')).getAllByText('DELAY')).toHaveLength(2);
    expect(within(screen.getByTestId('split-line-752')).getByText('ORDER 145')).toBeInTheDocument();
    expect(table.querySelector('[data-extra-row]')).not.toBeNull();
  });

  it('shows the values as plain text', () => {
    renderSheet(ownerSavedCase(), [480]);
    const text = screen.getByTestId('split-line-480').textContent ?? '';
    for (const part of ['14', '236', '167', '20/09/2026', '20/11/2026']) expect(text).toContain(part);
  });

  it('renders no input, no date picker, no button of any kind', () => {
    const { table } = renderSheet(ownerSavedCase(), [480, 752]);
    expect(table.querySelectorAll('input, textarea, select')).toHaveLength(0);
    expect(within(table).queryAllByRole('button')).toHaveLength(0);
  });

  it('renders no grip, no "N left" chip, no Balance cell, no "+ Split", no remove x', () => {
    const { table } = renderSheet(ownerSavedCase(), [480, 752]);
    expect(table.querySelectorAll('[data-drag-handle]')).toHaveLength(0);
    expect(screen.queryByTestId('balance-480')).not.toBeInTheDocument();
    expect(screen.queryByTestId('balance-752')).not.toBeInTheDocument();
    expect(table.textContent).not.toMatch(/\d+ left/);
    expect(screen.queryByRole('button', { name: /Add a split to line/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Remove split/ })).not.toBeInTheDocument();
  });

  it('keyboard does nothing: typing and Ctrl+Enter call no handler', () => {
    const { table, h } = renderSheet(ownerSavedCase(), [480]);
    fireEvent.keyDown(table, { key: '5' });
    fireEvent.keyDown(table, { key: 'Enter', ctrlKey: true });
    fireEvent.keyDown(screen.getByTestId('split-line-480'), { key: 'Delete' });
    for (const fn of Object.values(h)) expect(fn).not.toHaveBeenCalled();
  });

  it('draws a split that moved onto another line under that line, its LINE cell naming the origin', () => {
    renderSheet(receivingCase(), [480, 608]);
    const under608 = screen.getByTestId('split-line-608');
    const rows = Array.from(under608.querySelectorAll('tr'));
    const moved = rows.find((r) => (r.textContent ?? '').includes('236'));
    expect(moved, under608.textContent ?? '').toBeDefined();
    expect(Array.from((moved as HTMLTableRowElement).cells).some((td) => (td.textContent ?? '').trim() === '480')).toBe(true);
  });
});
