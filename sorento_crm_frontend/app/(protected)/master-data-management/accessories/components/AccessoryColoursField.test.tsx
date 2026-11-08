/**
 * PRICETAG-ACCESSORY-DESIGNER S7: an accessory's colours are their own ordered list, not tied to pictures.
 * Plan: "S7 Pictures and colours are independent" (owner hand test: "the custom colour picker must be like the
 * colour picker instead of need me type in"). Written test-FIRST: `./AccessoryColoursField` does not exist.
 *
 * Invented names (the coder must match them), all from `./AccessoryColoursField` (named export):
 *   <AccessoryColoursField colours={[{ name, hex }]} canEdit onChange={(next: {name, hex}[]) => void} />
 *   section label "Colours"; one list item per colour; per row
 *     - a swatch button of the shared `components/common/ColorPicker` (title = the hex), which opens the
 *       spectrum popover (sliders "Saturation and brightness" and "Hue")
 *     - a name input labelled "Colour name N" whose placeholder is the preset name when the hex matches
 *       Black #1f2937 / Grey #9ca3af / Silver #c0c0c0 / White #ffffff / Gold #d4af37 / Gunmetal #2c3539
 *     - a drag handle button "Reorder colour N" and a button "Remove colour N"
 *   a button "Add colour" appends a row (default Black #1f2937)
 * The real ColorPicker is used (not mocked): the control must be the picker, not only a typed hex box.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { AccessoryColoursField } from './AccessoryColoursField';

type Colour = { name: string | null; hex: string };
const BLACK: Colour = { name: 'Black', hex: '#1f2937' };
const GREY: Colour = { name: 'Grey', hex: '#9ca3af' };

function Harness({ initial, spy }: { initial: Colour[]; spy: (next: Colour[]) => void }) {
  const [colours, setColours] = useState(initial);
  return (
    <AccessoryColoursField
      colours={colours}
      canEdit
      onChange={(next: Colour[]) => {
        spy(next);
        setColours(next);
      }}
    />
  );
}

function mount(initial: Colour[] = [BLACK, GREY]) {
  const spy = vi.fn();
  render(<Harness initial={initial} spy={spy} />);
  return spy;
}

const rows = () => screen.getAllByRole('listitem');

describe('AccessoryColoursField', () => {
  it('has a Colours section with one row per colour', () => {
    mount();
    expect(screen.getByText('Colours')).toBeInTheDocument();
    expect(rows()).toHaveLength(2);
    expect(screen.getByLabelText('Colour name 1')).toHaveValue('Black');
    expect(screen.getByLabelText('Colour name 2')).toHaveValue('Grey');
  });

  it('each row has a swatch button showing its colour', () => {
    mount();
    const swatches = rows().map((row) => within(row).getByTitle(/^#/));
    expect(swatches.map((s) => s.getAttribute('title'))).toEqual(['#1f2937', '#9ca3af']);
  });

  it('the swatch opens the shared colour picker with its spectrum and hue sliders', () => {
    mount();
    fireEvent.click(within(rows()[0]).getByTitle('#1f2937'));
    expect(screen.getByRole('slider', { name: 'Saturation and brightness' })).toBeInTheDocument();
    expect(screen.getByRole('slider', { name: 'Hue' })).toBeInTheDocument();
  });

  it('picking a colour in the picker reports [{ name, hex }]', () => {
    const spy = mount();
    fireEvent.click(within(rows()[1]).getByTitle('#9ca3af'));
    const hex = within(rows()[1]).getAllByLabelText(/^Hex/)[0];
    fireEvent.change(hex, { target: { value: '#12ab34' } });
    fireEvent.keyDown(hex, { key: 'Enter' });
    expect(spy).toHaveBeenLastCalledWith([BLACK, { name: 'Grey', hex: '#12ab34' }]);
  });

  it('editing a name reports it and keeps the hex', () => {
    const spy = mount();
    fireEvent.change(screen.getByLabelText('Colour name 1'), { target: { value: 'Matt black' } });
    expect(spy).toHaveBeenLastCalledWith([{ name: 'Matt black', hex: '#1f2937' }, GREY]);
  });

  it('a blank name is reported as null or an empty string, never dropped', () => {
    const spy = mount();
    fireEvent.change(screen.getByLabelText('Colour name 1'), { target: { value: '' } });
    const [first] = spy.mock.calls.at(-1)![0] as Colour[];
    expect(first.hex).toBe('#1f2937');
    expect(first.name ?? '').toBe('');
  });

  it('shows the preset name as the placeholder when a colour has no name', () => {
    mount([{ name: null, hex: '#d4af37' }, { name: null, hex: '#123456' }]);
    expect(screen.getByLabelText('Colour name 1')).toHaveAttribute('placeholder', 'Gold');
    expect(screen.getByLabelText('Colour name 2').getAttribute('placeholder') ?? '').not.toBe('Gold');
  });

  it('Add colour appends a row, Black by default', () => {
    const spy = mount([GREY]);
    fireEvent.click(screen.getByRole('button', { name: 'Add colour' }));
    const next = spy.mock.calls.at(-1)![0] as Colour[];
    expect(next).toHaveLength(2);
    expect(next[0]).toEqual(GREY);
    expect(next[1].hex).toBe('#1f2937');
    expect(rows()).toHaveLength(2);
  });

  it('Remove colour drops that row only', () => {
    const spy = mount();
    fireEvent.click(screen.getByRole('button', { name: 'Remove colour 1' }));
    expect(spy).toHaveBeenLastCalledWith([GREY]);
    expect(rows()).toHaveLength(1);
  });

  it('has a drag handle per colour to order them', () => {
    mount();
    expect(screen.getAllByRole('button', { name: /^Reorder colour/ })).toHaveLength(2);
  });

  it('an accessory with no colours shows only Add colour', () => {
    mount([]);
    expect(screen.queryAllByRole('listitem')).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Add colour' })).toBeInTheDocument();
  });

  it('read-only: no Add, Remove or Reorder, and no editable name', () => {
    render(<AccessoryColoursField colours={[BLACK]} canEdit={false} onChange={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Add colour' })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Remove colour/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Reorder colour/ })).toBeNull();
    expect(screen.getByText('Black')).toBeInTheDocument();
  });
});
