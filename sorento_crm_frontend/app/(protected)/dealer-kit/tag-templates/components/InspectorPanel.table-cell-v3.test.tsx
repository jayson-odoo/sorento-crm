/**
 * SPEC-SHEET-PARITY-B2 v3 editor, AC-C3.4: the table Inspector's Cell section loses the "Cell row" /
 * "Cell column" number boxes and the raw Content box (a cell is picked and typed on the page) and
 * gains "Row height" and "Column width" for the selected cell's row / column; border, fill and
 * padding stay. Shared InspectorPanel, so the same in both designers. Written test-FIRST.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div data-testid="select" />,
}));

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { InspectorPanel } from './InspectorPanel';

const side = { color: '#000000', width_mm: 0.2 };
const cell = (text: string) => ({ text, padding_mm: 1, border: { top: side, right: side, bottom: side, left: side } });

function tableLayer(): TagLayer {
  return {
    id: 'tbl',
    type: 'table',
    x_mm: 0,
    y_mm: 0,
    width_mm: 60,
    height_mm: 30,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'table',
      columns: [{ width_mm: 20 }, { width_mm: 40 }],
      rows: [{ height_mm: 6 }, { height_mm: 9 }, { height_mm: 12 }],
      cells: [
        [cell('REF'), cell('{{doc.ref}}')],
        [cell('Code'), cell('{{product.code}}')],
        [cell('Size'), cell('')],
      ],
      fontFamily: 'DM Sans',
      fontSize: 10,
      color: '#000000',
      align: 'left',
      verticalAlign: 'middle',
    },
  } as unknown as TagLayer;
}

function mount(tableCell = { row: 1, col: 1 }) {
  const onUpdateProps = vi.fn();
  render(
    <InspectorPanel
      layer={tableLayer()}
      onUpdate={vi.fn()}
      onUpdateProps={onUpdateProps}
      tableCell={tableCell}
      onInsertField={vi.fn()}
    />,
  );
  return onUpdateProps;
}

describe('table Inspector Cell section (AC-C3.4)', () => {
  it('has no Cell row / Cell column boxes and no raw Content box', () => {
    mount();
    expect(screen.queryByLabelText('Cell row')).toBeNull();
    expect(screen.queryByLabelText('Cell column')).toBeNull();
    expect(screen.queryByLabelText('Cell content')).toBeNull();
    expect(screen.queryByText('{{product.code}}')).toBeNull();
    expect(screen.queryByDisplayValue('{{product.code}}')).toBeNull();
  });

  it('keeps border colour, border width, padding and fill', () => {
    mount();
    expect(screen.getByLabelText('Border width')).toBeInTheDocument();
    expect(screen.getByLabelText('Padding')).toBeInTheDocument();
    expect(screen.getAllByText(/Border colour/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^Fill$/).length).toBeGreaterThan(0);
  });

  it('shows Row height and Column width of the selected cell row / column', () => {
    mount({ row: 1, col: 1 });
    expect((screen.getByLabelText(/^Row height/) as HTMLInputElement).value).toBe('9');
    expect((screen.getByLabelText(/^Column width/) as HTMLInputElement).value).toBe('40');
  });

  it('follows the selected cell', () => {
    mount({ row: 2, col: 0 });
    expect((screen.getByLabelText(/^Row height/) as HTMLInputElement).value).toBe('12');
    expect((screen.getByLabelText(/^Column width/) as HTMLInputElement).value).toBe('20');
  });

  it('Row height writes that row height_mm and nothing else', () => {
    const onUpdateProps = mount({ row: 1, col: 1 });
    fireEvent.change(screen.getByLabelText(/^Row height/), { target: { value: '30' } });
    const [id, changes] = onUpdateProps.mock.calls.at(-1)!;
    expect(id).toBe('tbl');
    expect((changes as { rows: { height_mm: number }[] }).rows.map((r) => r.height_mm)).toEqual([6, 30, 12]);
  });

  it('Column width writes that column width_mm', () => {
    const onUpdateProps = mount({ row: 1, col: 0 });
    fireEvent.change(screen.getByLabelText(/^Column width/), { target: { value: '25' } });
    const [, changes] = onUpdateProps.mock.calls.at(-1)!;
    expect((changes as { columns: { width_mm: number }[] }).columns[0].width_mm).toBe(25);
  });
});
