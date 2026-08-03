/**
 * The line table that behaves like a spreadsheet.
 *
 * What is pinned here is the BEHAVIOUR the client asked for, not the markup: a row is added
 * inline and takes the caret, a cell is edited where it sits, Tab walks and rolls onto the
 * next row, Enter drops down, Escape puts one cell back, the total moves while a quantity is
 * typed, a row that cannot be saved marks the cell at fault instead of vanishing, and
 * removing a row asks first.
 *
 * Values stay STRINGS end to end: what is typed is what the caller is handed.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({
  toast: {
    custom: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
  },
}));

import {
  InlineLineTable,
  type InlineDraft,
  type InlineLineColumn,
} from './InlineLineTable';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

interface Row {
  id: string;
  code: string;
  description: string;
  quantity: string;
  unit_price: string;
  notes: string;
}

const UNITS = [
  { value: 'pcs', label: 'Pieces' },
  { value: 'set', label: 'Sets' },
];

function row(overrides: Partial<Row> = {}): Row {
  return {
    id: 'r1',
    code: 'pcs',
    description: 'Wall-hung WC',
    quantity: '2',
    unit_price: '900.00',
    notes: '',
    ...overrides,
  };
}

const onCreate = vi.fn<(draft: InlineDraft) => Promise<void>>(async () => {});
const onUpdate = vi.fn<(row: Row, draft: InlineDraft) => Promise<void>>(async () => {});
const onDelete = vi.fn<(row: Row) => Promise<void>>(async () => {});

function columns(): InlineLineColumn<Row>[] {
  return [
    {
      key: 'description',
      header: 'Description',
      width: 200,
      kind: 'text',
    },
    {
      key: 'quantity',
      header: 'Qty',
      width: 90,
      kind: 'number',
      align: 'end',
      validate: (value) => (/^\d*\.?\d*$/.test(value) ? null : 'Must be a number'),
    },
    {
      key: 'unit_price',
      header: 'Unit price',
      width: 120,
      kind: 'number',
      align: 'end',
    },
    {
      key: 'code',
      header: 'Unit',
      width: 120,
      kind: 'select',
      options: UNITS,
      resolveSelected: (_row, draft) => UNITS.find((unit) => unit.value === draft.code),
    },
    {
      key: 'total',
      header: 'Total',
      width: 120,
      kind: 'derived',
      align: 'end',
      derive: (draft) =>
        `RM ${(Number(draft.quantity || 0) * Number(draft.unit_price || 0)).toFixed(2)}`,
    },
  ];
}

function toDraft(item: Row): InlineDraft {
  return {
    description: item.description,
    quantity: item.quantity,
    unit_price: item.unit_price,
    code: item.code,
    notes: item.notes,
  };
}

function emptyDraft(): InlineDraft {
  return { description: '', quantity: '1', unit_price: '', code: '', notes: '' };
}

function renderTable(props: Partial<React.ComponentProps<typeof InlineLineTable<Row>>> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <InlineLineTable<Row>
        rows={[row()]}
        getRowId={(item) => item.id}
        columns={columns()}
        toDraft={toDraft}
        emptyDraft={emptyDraft}
        onCreate={onCreate}
        onUpdate={onUpdate}
        onDelete={onDelete}
        describeRow={(item, index) => item?.code ?? `line ${index + 1}`}
        rowDetail={{ key: 'notes', label: 'Notes' }}
        validateRow={(draft): Record<string, string> =>
          draft.description.trim() ? {} : { description: 'Needed' }
        }
        {...props}
      />
    </QueryClientProvider>,
  );
}

function cell(name: string) {
  return screen.getByRole('textbox', { name });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('InlineLineTable', () => {
  it('keeps its header and its add row when there is nothing in it', () => {
    renderTable({ rows: [], emptyHint: 'Nothing quoted yet.' });

    // The header survives an empty table: a person about to type needs to see the shape
    // of what they are about to type into.
    expect(screen.getByRole('columnheader', { name: 'Description' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Qty' })).toBeInTheDocument();
    expect(screen.getByText('Nothing quoted yet.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add a line' })).toBeInTheDocument();
  });

  it('appends an editable row inline and puts the caret in its first cell', async () => {
    renderTable({ rows: [] });

    fireEvent.click(screen.getByRole('button', { name: 'Add a line' }));

    const added = await screen.findByRole('textbox', { name: 'Description on line 1' });
    await waitFor(() => expect(document.activeElement).toBe(added));
    // No dialog opened; the row IS the form.
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('keeps a freshly added row alive when its picker is opened', async () => {
    // The client hit this: click Add a line, click the product dropdown, and the row
    // vanished before anything could be picked. Opening a Radix popover fires focusout
    // on the row with a NULL relatedTarget, which read as "the caret left the table" and
    // sent the untouched row down the discard path. Focus has not left the row: it has
    // gone into the row's own popover.
    renderTable({ rows: [] });
    fireEvent.click(screen.getByRole('button', { name: 'Add a line' }));
    await screen.findByRole('textbox', { name: 'Description on line 1' });

    const picker = screen.getByRole('combobox', { name: 'Unit on line 1' });
    fireEvent.focusOut(picker, { relatedTarget: null });
    fireEvent.click(picker);

    expect(
      screen.getByRole('textbox', { name: 'Description on line 1' }),
    ).toBeInTheDocument();
  });

  it('leaves an untouched added row waiting rather than discarding it', async () => {
    // Removing a row is the Remove button's job, and that asks first. Nothing the user
    // does with the caret should make a row disappear underneath them.
    renderTable({ rows: [] });
    fireEvent.click(screen.getByRole('button', { name: 'Add a line' }));
    const added = await screen.findByRole('textbox', { name: 'Description on line 1' });

    const outside = document.createElement('button');
    document.body.appendChild(outside);
    fireEvent.focusOut(added, { relatedTarget: outside });

    await waitFor(() =>
      expect(
        screen.getByRole('textbox', { name: 'Description on line 1' }),
      ).toBeInTheDocument(),
    );
    // And it was not saved either: nothing was typed, so there is nothing to send.
    expect(onCreate).not.toHaveBeenCalled();
  });

  it('edits a text cell and a number cell where they sit', () => {
    renderTable();

    fireEvent.change(cell('Description on pcs'), { target: { value: 'Rimless WC' } });
    fireEvent.change(cell('Qty on pcs'), { target: { value: '12' } });

    expect(cell('Description on pcs')).toHaveValue('Rimless WC');
    expect(cell('Qty on pcs')).toHaveValue('12');
  });

  it('picks a value in a select cell through the searchable dropdown', async () => {
    renderTable();

    fireEvent.click(screen.getByRole('combobox', { name: 'Unit on pcs' }));
    fireEvent.click(await screen.findByRole('option', { name: 'Sets' }));

    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Unit on pcs' })).toHaveTextContent('Sets'),
    );
  });

  it('recomputes the line total while the quantity is being typed', () => {
    renderTable();

    expect(screen.getByText('RM 1800.00')).toBeInTheDocument();

    fireEvent.change(cell('Qty on pcs'), { target: { value: '3' } });

    // Nothing was saved and nothing was refetched: the number moved off the draft.
    expect(screen.getByText('RM 2700.00')).toBeInTheDocument();
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it('walks across the row with Tab and rolls onto the next one', async () => {
    renderTable({ rows: [row(), row({ id: 'r2', code: 'set' })] });

    const first = cell('Description on pcs');
    first.focus();

    fireEvent.keyDown(first, { key: 'Tab' });
    expect(document.activeElement).toBe(cell('Qty on pcs'));

    fireEvent.keyDown(document.activeElement!, { key: 'Tab' });
    expect(document.activeElement).toBe(cell('Unit price on pcs'));

    // Last editable cell of the row is the select, so Tab from it lands on the next row.
    fireEvent.keyDown(document.activeElement!, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByRole('combobox', { name: 'Unit on pcs' }));

    fireEvent.keyDown(document.activeElement!, { key: 'Tab' });
    await waitFor(() =>
      expect(document.activeElement).toBe(cell('Description on set')),
    );
  });

  it('walks backwards with Shift-Tab and rolls onto the previous row', async () => {
    renderTable({ rows: [row(), row({ id: 'r2', code: 'set' })] });

    const second = cell('Description on set');
    second.focus();

    fireEvent.keyDown(second, { key: 'Tab', shiftKey: true });
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole('combobox', { name: 'Unit on pcs' }),
      ),
    );
  });

  it('drops down a row on Enter', async () => {
    renderTable({ rows: [row(), row({ id: 'r2', code: 'set' })] });

    const first = cell('Qty on pcs');
    first.focus();
    fireEvent.keyDown(first, { key: 'Enter' });

    await waitFor(() => expect(document.activeElement).toBe(cell('Qty on set')));
  });

  it('puts one cell back on Escape, and leaves the rest of the row alone', () => {
    renderTable();

    fireEvent.change(cell('Description on pcs'), { target: { value: 'Changed' } });
    fireEvent.change(cell('Qty on pcs'), { target: { value: '9' } });

    fireEvent.keyDown(cell('Description on pcs'), { key: 'Escape' });

    expect(cell('Description on pcs')).toHaveValue('Wall-hung WC');
    expect(cell('Qty on pcs')).toHaveValue('9');
  });

  it('marks the cell at fault instead of dropping the row or raising a toast', async () => {
    renderTable();

    fireEvent.change(cell('Description on pcs'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save pcs' }));

    expect(await screen.findByText('Needed')).toBeInTheDocument();
    expect(cell('Description on pcs')).toHaveAttribute('aria-invalid', 'true');
    // The row is still there, still holding what was typed, and nothing was sent.
    expect(onUpdate).not.toHaveBeenCalled();

    // Fixing the cell clears the mark without a second attempt.
    fireEvent.change(cell('Description on pcs'), { target: { value: 'Rimless WC' } });
    expect(screen.queryByText('Needed')).toBeNull();
  });

  it('marks a per-cell shape error on the cell that holds it', async () => {
    renderTable();

    fireEvent.change(cell('Qty on pcs'), { target: { value: 'twelve' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save pcs' }));

    expect(await screen.findByText('Must be a number')).toBeInTheDocument();
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it('saves a row when the caret moves on to another row, the way a spreadsheet does', async () => {
    renderTable({ rows: [row(), row({ id: 'r2', code: 'set' })] });

    const first = cell('Qty on pcs');
    first.focus();
    fireEvent.change(first, { target: { value: '12' } });

    cell('Qty on set').focus();

    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
    expect(onUpdate.mock.calls[0][1]).toMatchObject({ quantity: '12' });
  });

  it('leaves a clean row alone when the caret passes through it', async () => {
    renderTable({ rows: [row(), row({ id: 'r2', code: 'set' })] });

    cell('Qty on pcs').focus();
    cell('Qty on set').focus();

    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it('saves an edited row through the caller, as strings', async () => {
    renderTable();

    fireEvent.change(cell('Qty on pcs'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save pcs' }));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
    expect(onUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'r1' }),
      expect.objectContaining({ quantity: '12', unit_price: '900.00' }),
    );
  });

  it('creates an added row through the caller, carrying fields that have no column', async () => {
    renderTable({ rows: [] });

    fireEvent.click(screen.getByRole('button', { name: 'Add a line' }));
    const description = await screen.findByRole('textbox', {
      name: 'Description on line 1',
    });
    fireEvent.change(description, { target: { value: 'Bespoke vanity top' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save line 1' }));

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    expect(onCreate).toHaveBeenCalledWith({
      description: 'Bespoke vanity top',
      quantity: '1',
      unit_price: '',
      code: '',
      notes: '',
    });
  });

  it('creates an added row once, however many times the save is asked for', async () => {
    renderTable({ rows: [] });

    fireEvent.click(screen.getByRole('button', { name: 'Add a line' }));
    const description = await screen.findByRole('textbox', {
      name: 'Description on line 1',
    });
    fireEvent.change(description, { target: { value: 'First' } });

    // Two commit paths can meet on one row (focus leaving it, and the tick being pressed).
    // Whichever gets there first, the line goes onto the record once.
    const save = screen.getByRole('button', { name: 'Save line 1' });
    fireEvent.click(save);
    fireEvent.click(save);

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    expect(onCreate.mock.calls[0][0]).toMatchObject({ description: 'First' });
  });

  it('keeps the fields with no column in a per-row note, rather than losing them', async () => {
    renderTable();

    fireEvent.click(screen.getByRole('button', { name: 'Notes on pcs' }));
    const note = await screen.findByRole('textbox', { name: 'Notes on pcs' });
    fireEvent.change(note, { target: { value: 'Agreed with the QS on 3 July' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save pcs' }));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
    expect(onUpdate.mock.calls[0][1]).toMatchObject({
      notes: 'Agreed with the QS on 3 July',
    });
  });

  it('asks before removing a row, and only then removes it', async () => {
    renderTable();

    fireEvent.click(screen.getByRole('button', { name: 'Remove pcs' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/cannot be undone/i)).toBeInTheDocument();
    expect(onDelete).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ id: 'r1' })));
  });

  it('drops an added row nobody typed into without a question, since it holds nothing', async () => {
    renderTable({ rows: [] });

    fireEvent.click(screen.getByRole('button', { name: 'Add a line' }));
    await screen.findByRole('textbox', { name: 'Description on line 1' });

    fireEvent.click(screen.getByRole('button', { name: 'Remove line 1' }));

    await waitFor(() =>
      expect(screen.queryByRole('textbox', { name: 'Description on line 1' })).toBeNull(),
    );
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it('offers nothing to type into when it cannot be edited', () => {
    renderTable({ readOnly: true });

    expect(screen.getByRole('columnheader', { name: 'Description' })).toBeInTheDocument();
    expect(screen.getByText('Wall-hung WC')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a line' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Remove pcs' })).toBeNull();
  });
});
